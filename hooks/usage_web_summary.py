"""
Summary 生成模組 (AI 摘要 + 配額 + cache + dedup + claude CLI 呼叫).

从 usage-web.py 拆出, 通过 `import usage_web_summary as summary` 使用.
無外部依賴, 只靠 Python stdlib.
"""
import os
import json
import subprocess
import threading
from datetime import datetime

# ============================================================
# 常量
# ============================================================
CACHE_PATH = os.path.expanduser("~/.claude/usage-stats/summaries.json")
QUOTA_PATH = os.path.expanduser("~/.claude/usage-stats/summary-quota.json")
MODEL = os.environ.get("CLAUDE_SUMMARY_MODEL", "claude-haiku-4-5")
DAILY_LIMIT = int(os.environ.get("CLAUDE_SUMMARY_DAILY_LIMIT", "100"))
MAX_INFLIGHT = int(os.environ.get("CLAUDE_SUMMARY_MAX_INFLIGHT", "8"))
CLI = os.environ.get("CLAUDE_CLI", "claude")


# ============================================================
# 状态 + 锁
# ============================================================
def _load_json(path: str, default):
    if not os.path.isfile(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


_disk_cache = _load_json(CACHE_PATH, {})
_quota = _load_json(QUOTA_PATH, {"date": "", "count": 0})
_inflight = 0
_pending = 0

_cache_lock = threading.Lock()
_quota_lock = threading.Lock()
_inflight_events = {}  # path -> Event (同 path 去重)
_inflight_lock = threading.Lock()


def _save_json(path: str, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass


def _save_cache():
    _save_json(CACHE_PATH, _disk_cache)


def _save_quota():
    _save_json(QUOTA_PATH, _quota)


# ============================================================
# 配额 / 并发槽
# ============================================================
def _try_acquire_slot():
    """佔一個生成槽. 返回 (allowed, count, limit, error)."""
    global _inflight, _pending
    today = datetime.now().strftime("%Y-%m-%d")
    with _quota_lock:
        if _quota.get("date") != today:
            _quota["date"] = today
            _quota["count"] = 0
            _save_quota()
        count_now = _quota["count"]
        if count_now + _pending >= DAILY_LIMIT:
            return False, count_now, DAILY_LIMIT, "daily_limit"
        if _inflight >= MAX_INFLIGHT:
            return False, count_now, DAILY_LIMIT, "too_many_inflight"
        _inflight += 1
        _pending += 1
        return True, count_now, DAILY_LIMIT, ""


def _release_slot(success: bool):
    """釋放槽位. success=True 時 count +1 (成功才算配額)."""
    global _inflight, _pending
    with _quota_lock:
        _inflight = max(0, _inflight - 1)
        _pending = max(0, _pending - 1)
        if success:
            _quota["count"] = _quota.get("count", 0) + 1
            _save_quota()


def get_status() -> dict:
    """返回 {count, limit, cache_size, pending}."""
    today = datetime.now().strftime("%Y-%m-%d")
    with _quota_lock:
        count = _quota.get("count", 0) if _quota.get("date") == today else 0
        pending = _pending
    with _cache_lock:
        cache_size = len(_disk_cache)
    return {"count": count, "limit": DAILY_LIMIT, "cache_size": cache_size, "pending": pending}


def clear_cache() -> int:
    """清空磁碟 cache, 返回清掉的數量."""
    with _cache_lock:
        n = len(_disk_cache)
        _disk_cache.clear()
        _save_cache()
    return n


# ============================================================
# claude CLI 調用
# ============================================================
def call_claude(file_path: str, content: str):
    """通过 claude -p 子进程生成摘要. 返回 (summary, error)."""
    rel = os.path.basename(file_path)
    prompt = (
        "用一句极简中文概括下面文件的作用, 10-15 字, "
        "不要列要点, 不要 markdown, 不要前缀, 不要句末标点, 直接输出摘要文字.\n\n"
        f"文件名: {rel}\n\n内容:\n{content[:6000]}"
    )
    try:
        env = os.environ.copy()
        env["CLAUDE_SKIP_SESSION_START"] = "1"
        result = subprocess.run(
            [CLI, "-p", prompt, "--model", MODEL],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
    except FileNotFoundError:
        return "", f"未找到 {CLI} CLI"
    except subprocess.TimeoutExpired:
        return "", "claude CLI 超时 (60s)"
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()[:200]
        return "", f"claude CLI 退出码 {result.returncode}: {err}"
    text = (result.stdout or "").strip()
    for ch in ['"', "'", "「", "」", "*", "`"]:
        text = text.strip(ch)
    return text.strip(), ""


# ============================================================
# 主入口: 读 cache 或调 API 生成 (含 dedup)
# ============================================================
def get_or_generate(path: str):
    """讀緩存或調 API 生成. 同 path 並發請求自動去重.
    返回 (summary, from_cache, error, quota_info)."""
    if not path or not os.path.isfile(path):
        return "", False, "file not found", None
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return "", False, "stat failed", None

    # 第一次 cache 检查
    with _cache_lock:
        cached = _disk_cache.get(path)
    if cached and cached.get("mtime") == mtime and cached.get("summary"):
        return cached["summary"], True, "", None

    # 去重: 同 path 已在生成中 → 等領頭線程
    with _inflight_lock:
        ev = _inflight_events.get(path)
        is_leader = ev is None
        if is_leader:
            ev = threading.Event()
            _inflight_events[path] = ev

    if not is_leader:
        if not ev.wait(timeout=70):
            return "", False, "并发等待超时", None
        with _cache_lock:
            cached = _disk_cache.get(path)
        if cached and cached.get("mtime") == mtime and cached.get("summary"):
            return cached["summary"], True, "", None
        return "", False, "并发等待返回但缓存仍空", None

    # 領頭線程: 執行生成流程
    try:
        allowed, count, limit, q_err = _try_acquire_slot()
        quota_info = {"count": count, "limit": limit}
        if not allowed:
            if q_err == "daily_limit":
                return "", False, f"今日配额已用完 ({count}/{limit})", quota_info
            return "", False, "请求过密, 请稍后再试", quota_info
        success = False
        try:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(8192)
            except Exception as e:
                return "", False, f"read failed: {e}", quota_info
            text, err = call_claude(path, content)
            if err:
                return "", False, err, quota_info
            if not text:
                return "", False, "claude 返回空摘要", quota_info
            with _cache_lock:
                _disk_cache[path] = {"mtime": mtime, "summary": text}
                _save_cache()
            success = True
            return text, False, "", {"count": quota_info["count"] + 1, "limit": limit}
        finally:
            _release_slot(success)
    finally:
        ev.set()
        with _inflight_lock:
            _inflight_events.pop(path, None)
