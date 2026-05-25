"""AI 大事 seen 数据存取 + prune.

存在 NEWS_VOTES_PATH 同文件 (ai-news-feedback.json) 的 seen 段, 与 votes / favorites 平级.
独立模块避免 ai_news.render 反向 import shared.http.server (后者是 __main__,
反向 import 会触发模块二次加载).

并发: ThreadingHTTPServer 多线程同时写 (vote / favorite / seen POST 任意组合) 会
read-modify-write 同一个文件, 必须用 feedback_lock (RLock) 把整段事务包起来.
所有 save_news_* / 任何 load-then-save 都必须在锁内执行.
.tmp 路径加 pid 后缀防多进程共享路径冲突 (虽然单进程足够, belt-and-suspenders)."""
import json
import os
import threading
from datetime import datetime, timezone

from shared.infra.core import NEWS_VOTES_PATH


# 全文件级锁: 任何 load+modify+save 事务必须在 with feedback_lock 内执行
# RLock 允许同线程嵌套 (prune 内部调 save 都是同线程)
feedback_lock = threading.RLock()


def _tmp_path() -> str:
    """返回带 pid 后缀的 .tmp 路径, 防多进程并发共享 tmp."""
    return f"{NEWS_VOTES_PATH}.tmp.{os.getpid()}"


def load_news_seen() -> dict:
    """读 ai-news-feedback.json 的 seen 段, 返回 {url: {ts, source}}."""
    if not os.path.isfile(NEWS_VOTES_PATH):
        return {}
    try:
        with open(NEWS_VOTES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        seen = data.get("seen", {})
        return seen if isinstance(seen, dict) else {}
    except Exception:
        return {}


def save_news_seen(seen: dict):
    """写回 seen, 保留既有 votes / favorites. 原子 rename. 必须在 feedback_lock 内."""
    os.makedirs(os.path.dirname(NEWS_VOTES_PATH), exist_ok=True)
    existing = {}
    if os.path.isfile(NEWS_VOTES_PATH):
        try:
            with open(NEWS_VOTES_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f) or {}
        except Exception:
            existing = {}
    payload = {
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "votes": existing.get("votes", {}),
        "favorites": existing.get("favorites", {}),
        "seen": seen,
    }
    tmp = _tmp_path()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, NEWS_VOTES_PATH)


def prune_news_seen(current_urls: set) -> int:
    """裁剪 seen, 仅保留 current_urls 内的条目, 返回删除数量.
    无变化时不写盘. current_urls 为空时直接 noop, 避免 ai-news.json 临时空时把 seen 全清."""
    if not current_urls:
        return 0
    with feedback_lock:
        seen = load_news_seen()
        if not seen:
            return 0
        stale = [u for u in seen.keys() if u not in current_urls]
        if not stale:
            return 0
        for u in stale:
            seen.pop(u, None)
        try:
            save_news_seen(seen)
        except Exception:
            return 0
        return len(stale)
