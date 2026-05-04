#!/usr/bin/env python3
"""Core module: 常量 + 原子 helpers.
無其他業務依賴 (除 stdlib), 可被 queries/render/main 安全 import."""
import os
import sys
import time
from datetime import datetime, timedelta, timezone

#!/usr/bin/env python3
"""Usage stats dashboard implementation module.

从 usage-web.py 拆出: 常量、查询、分析、渲染、archive、security 全部在此.
usage-web.py 保留 HTTP Handler + main() 作为薄壳, 通过 `from usage_web_impl import *` 使用.
"""
import os
import time
from datetime import datetime, timedelta, timezone


# 仓库根 (cloud-sync 数据 + repo-relative 路径都基于此, 兼容 mac 和云端 routine 的不同根)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

DB_FILE = os.path.expanduser("~/Desktop/ai-project/data/events.db")
NEWS_JSON_PATH = os.path.join(_REPO_ROOT, "cloud-sync", "ai-news.json")
NEWS_VOTES_PATH = os.path.join(_REPO_ROOT, "cloud-sync", "ai-news-feedback.json")
NEWS_FETCHER_PATH = os.path.expanduser("~/Desktop/ai-project/hooks/fetch-ai-news.py")
PROJECT_ROOT = os.environ.get("LIVE_APP_PATH", "/Users/augus/Desktop/开发项目/live_app")
USER_HOME = os.path.expanduser("~")
# A4: memory 路径去硬编码
MEMORY_DIR = os.environ.get(
    "LIVE_APP_MEMORY_PATH",
    f"{USER_HOME}/.claude/auto-memory",
)

# ============================================================
# 事件类型统一定义 (单一真理源)
# 新增/删除事件类型只需改这里, 其他地方自动派生
# ============================================================
# (event_type, active_label, pairable)
# pairable=True 的事件在 active 区显示 paired 配对率
EVENT_TYPES = [
    ("skill_read",     "Skill 读取",        True),
    ("skill_explicit", "显式 Skill 调用",   False),
    ("subagent",       "Subagent 派发",     False),
    ("clinerule_read", ".clinerules 读取",  True),
    ("claude_md_read", "CLAUDE.md 读取",    True),
    ("agents_md_read", "AGENTS.md 读取",    True),
    ("memory_read",    "memory 读取",       True),
]
# 派生 (不要手改, 从 EVENT_TYPES 自动同步)
CATEGORIES = [(t, l) for t, l, _ in EVENT_TYPES]

# 通用文案映射（英文 type 内部不动，只翻译展示层）
LABELS = {
    "title":              "Claude Code 使用统计",
    "active_usage":       "已触发",
    "cold_candidates":    "装饰品候选（0 触发）",
    "events_in_window":   "窗口内事件数",
    "scope":              "范围",
    "refresh_hint":       "刷新页面可更新数据",
    "all_hot":            "(全部已触发)",
    "none":               "(无数据)",
    "cold_skills":        "未触发 Skill 读取",
    "cold_skills_explicit": "未触发 Skill 调用",
    "cold_subagents":     "未触发 Subagent",
    "cold_clinerules":    "未触发 .clinerules",
    "cold_claude_md":     "未触发 CLAUDE.md",
    "cold_memory":        "未触发 memory",
    "cold_agents_md":     "未触发 AGENTS.md",
    "cold_plugins":       "未触发 Plugin 命令",
    "today_panel":        "跨项目 Today",
    "memory_panel":       "Memory 全部",
    "compact_panel":      "Compact 存档时间轴",
    "news_panel":         "每日 AI 大事",
    "claude_md_analysis": "CLAUDE.md 热度分析",
}


def cutoff_ts(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ============================================================
# 区块: Owner 解析与路径反查
# ============================================================
SUBPROJECT_MAP = {
    "clients/live3_app": "live3_app",
    "services/live4_go_talk": "live4_go_talk",
    "services/live3_svr_api": "live3_svr_api",
    "services/live3_svr_im": "live3_svr_im",
    "services/live3_svr_pay": "live3_svr_pay",
    "admin/live3_svr_admin": "live3_svr_admin",
}
SUBPROJECT_NAMES_FLAT = set(SUBPROJECT_MAP.values())


def compute_owner(path: str) -> str:
    """根据文件路径计算 owner 标签.
    global / live_app / 子项目名 / plugin 之一."""
    if not path:
        return "unknown"
    try:
        real = os.path.realpath(path)
    except Exception:
        return "unknown"
    user_claude = os.path.realpath(f"{USER_HOME}/.claude")
    project_real = os.path.realpath(PROJECT_ROOT)
    memory_real = os.path.realpath(MEMORY_DIR)
    plugins_root = os.path.realpath(f"{USER_HOME}/.claude/plugins")
    # memory 物理在 ~/.claude/auto-memory/ 但语义归项目
    if real == memory_real or real.startswith(memory_real + os.sep):
        return "live_app"
    # plugin skill 单独归类
    if real.startswith(plugins_root + os.sep):
        return "plugin"
    if real == user_claude or real.startswith(user_claude + os.sep):
        return "global"
    if real == project_real or real.startswith(project_real + os.sep):
        rel = os.path.relpath(real, project_real)
        parts = rel.split(os.sep)
        # 子项目目录匹配
        for sub_path, sub_name in SUBPROJECT_MAP.items():
            if rel == sub_path or rel.startswith(sub_path + os.sep):
                return sub_name
        # .clinerules/live3_app.md -> live3_app
        if parts[0] == ".clinerules":
            if len(parts) == 2 and parts[1].endswith(".md"):
                stem = parts[1][:-3]
                if stem in SUBPROJECT_NAMES_FLAT:
                    return stem
            # .clinerules/references/live3_app/... -> live3_app
            if len(parts) >= 3 and parts[1] == "references" and parts[2] in SUBPROJECT_NAMES_FLAT:
                return parts[2]
        return "live_app"
    return "unknown"


_PLUGIN_SKILL_CACHE = None
_PLUGIN_CACHE_TS = 0.0
_PLUGIN_CACHE_TTL = 600  # 10 分钟, 避免新装 plugin 后需要重启 server 才能被发现


def build_plugin_skill_cache():
    """扫描 ~/.claude/plugins/cache/ 构建 plugin:cmd -> path 映射."""
    global _PLUGIN_SKILL_CACHE, _PLUGIN_CACHE_TS
    cache = {}
    import glob
    for cmd_md in glob.glob(f"{USER_HOME}/.claude/plugins/cache/*/*/*/commands/*.md"):
        parts = cmd_md.split(os.sep)
        if len(parts) < 5:
            continue
        plugin = parts[-4]
        cmd_name = os.path.basename(cmd_md)[:-3]
        key = f"{plugin}:{cmd_name}"
        if key not in cache:
            cache[key] = cmd_md
    _PLUGIN_SKILL_CACHE = cache
    _PLUGIN_CACHE_TS = time.time()


def ensure_plugin_skill_cache():
    """按需重建 plugin skill 缓存, TTL 10 分钟."""
    global _PLUGIN_SKILL_CACHE
    if _PLUGIN_SKILL_CACHE is None or (time.time() - _PLUGIN_CACHE_TS) > _PLUGIN_CACHE_TTL:
        build_plugin_skill_cache()


def resolve_skill_path(name: str, scope: str) -> str:
    """反查 skill_explicit 事件对应的 SKILL.md 或 plugin command 路径."""
    # plugin:cmd 名字 (含冒号) 走 plugin 缓存
    if ":" in name:
        ensure_plugin_skill_cache()
        return _PLUGIN_SKILL_CACHE.get(name, "")
    candidates = []
    if scope == "user" or not scope:
        candidates.append(f"{USER_HOME}/.claude/skills/{name}/SKILL.md")
    if scope == "project" or not scope:
        candidates.append(f"{PROJECT_ROOT}/.claude/skills/{name}/SKILL.md")
    if not scope:
        for p in candidates:
            if os.path.isfile(p):
                return p
        return ""
    return candidates[0] if os.path.isfile(candidates[0]) else ""


def resolve_subagent_path(name: str) -> str:
    """反查 subagent 对应的定义文件, project 优先."""
    for p in [f"{PROJECT_ROOT}/.claude/agents/{name}.md",
              f"{USER_HOME}/.claude/agents/{name}.md"]:
        if os.path.isfile(p):
            return p
    return ""


def list_memory_browser(days: int = 7):
    """Memory 文件浏览: 返回按 mtime 倒序的 [(name, path, mtime, size)]."""
    if not os.path.isdir(MEMORY_DIR):
        return []
    out = []
    for f in os.listdir(MEMORY_DIR):
        if f.endswith(".md"):
            full = os.path.join(MEMORY_DIR, f)
            try:
                stat = os.stat(full)
                out.append((f[:-3], full, stat.st_mtime, stat.st_size))
            except OSError:
                pass
    out.sort(key=lambda x: x[2], reverse=True)
    return out


def list_compact_notes():
    """Compact-notes 浏览: 返回所有 compact 存档文件 [(name, path, mtime)]."""
    out = []
    locations = [
        f"{USER_HOME}/.claude/compact-notes",
        f"{PROJECT_ROOT}/compact-notes",
    ]
    for loc in locations:
        if not os.path.isdir(loc):
            continue
        for root, _, files in os.walk(loc):
            for f in files:
                if f.endswith(".md"):
                    full = os.path.join(root, f)
                    try:
                        mtime = os.stat(full).st_mtime
                        rel = os.path.relpath(full, loc)
                        out.append((rel, full, mtime))
                    except OSError:
                        pass
    out.sort(key=lambda x: x[2], reverse=True)
    return out




# 空数据状态统一定义 (#3)
EMPTY_STATES = {
    "no_data":       "(此范围内无数据)",
    "all_hot":       "(全部已触发)",
    "never_fired":   "从未触发",
    "none":          "(无数据)",
    "no_events":     "当前时间窗内暂无事件",
    "no_sessions":   "当前时间窗内无活跃会话",
    "no_owner":      "此目录归属下暂无对象",
}


def days_ago(ts_iso: str) -> int:
    """ISO 字符串转成'距今多少天'."""
    try:
        dt = datetime.strptime(ts_iso.rstrip("Z"), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return max(0, delta.days)
    except Exception:
        return -1


def fmt_local_time(ts_iso: str, fmt: str = "%H:%M") -> str:
    """ISO UTC 字符串转本机时间格式 (默认 HH:MM)."""
    if not ts_iso:
        return ""
    try:
        dt = datetime.strptime(ts_iso.rstrip("Z"), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime(fmt)
    except Exception:
        return ""


def fmt_relative_time(ts_iso: str) -> str:
    """相對日期 + 時間: 今日 HH:MM / 昨 HH:MM / MM-DD HH:MM."""
    if not ts_iso:
        return ""
    try:
        dt = datetime.strptime(ts_iso.rstrip("Z"), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        local = dt.astimezone()
    except Exception:
        return ""
    today = datetime.now().astimezone().date()
    delta = (today - local.date()).days
    if delta == 0:
        return local.strftime("%H:%M")
    if delta == 1:
        return "昨 " + local.strftime("%H:%M")
    return local.strftime("%m-%d %H:%M")


# ============================================================
# 区块: 文件系统枚举 (cold detection 的 universe 来源)
# ============================================================
def list_skill_files():
    """返回 [dict]. 每项: {name, scope, path, owner, disabled}. 含 .disabled/."""
    out = []
    for d, scope in [(f"{USER_HOME}/.claude/skills", "user"),
                     (f"{PROJECT_ROOT}/.claude/skills", "project")]:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.startswith(".") or name == ".disabled":
                continue
            full = os.path.join(d, name, "SKILL.md")
            if os.path.isfile(full):
                out.append({
                    "name": name, "scope": scope, "path": full,
                    "owner": compute_owner(full), "disabled": False,
                })
        disabled_dir = os.path.join(d, ".disabled")
        if os.path.isdir(disabled_dir):
            for name in sorted(os.listdir(disabled_dir)):
                full = os.path.join(disabled_dir, name, "SKILL.md")
                if os.path.isfile(full):
                    out.append({
                        "name": name, "scope": scope, "path": full,
                        "owner": compute_owner(full), "disabled": True,
                    })
    return out


def list_subagent_files():
    """返回 [dict]. 每项: {name, scope, path, owner, disabled}. 含 .disabled/."""
    out = []
    for d, scope in [(f"{USER_HOME}/.claude/agents", "user"),
                     (f"{PROJECT_ROOT}/.claude/agents", "project")]:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.startswith("."):
                continue
            if name.endswith(".md"):
                full = os.path.join(d, name)
                out.append({
                    "name": name[:-3], "scope": scope, "path": full,
                    "owner": compute_owner(full), "disabled": False,
                })
        disabled_dir = os.path.join(d, ".disabled")
        if os.path.isdir(disabled_dir):
            for name in sorted(os.listdir(disabled_dir)):
                if name.endswith(".md"):
                    full = os.path.join(disabled_dir, name)
                    out.append({
                        "name": name[:-3], "scope": scope, "path": full,
                        "owner": compute_owner(full), "disabled": True,
                    })
    return out


def list_clinerules():
    """返回 [dict]. 每项: {name (相对路径), scope, path, owner}."""
    root = f"{PROJECT_ROOT}/.clinerules"
    out = []
    if not os.path.isdir(root):
        return out
    for dirpath, _, files in os.walk(root):
        for f in sorted(files):
            if f.endswith(".md"):
                full = os.path.join(dirpath, f)
                rel = os.path.relpath(full, root)
                out.append({
                    "name": rel, "scope": "project", "path": full,
                    "owner": compute_owner(full),
                })
    return out


def list_claude_mds():
    """返回 [dict]. 每项: {name, scope, path, owner}."""
    out = []
    global_md = f"{USER_HOME}/.claude/CLAUDE.md"
    if os.path.isfile(global_md):
        out.append({"name": "global", "scope": "global", "path": global_md,
                    "owner": compute_owner(global_md)})
    root_md = f"{PROJECT_ROOT}/CLAUDE.md"
    if os.path.isfile(root_md):
        out.append({"name": "root", "scope": "project", "path": root_md,
                    "owner": compute_owner(root_md)})
    for sub_path in SUBPROJECT_MAP:
        md = f"{PROJECT_ROOT}/{sub_path}/CLAUDE.md"
        if os.path.isfile(md):
            out.append({"name": sub_path, "scope": "subproject", "path": md,
                        "owner": compute_owner(md)})
    return out


def list_agents_mds():
    """返回 [dict]. 每项: {name, scope, path, owner}."""
    out = []
    global_md = f"{USER_HOME}/.claude/AGENTS.md"
    if os.path.isfile(global_md):
        out.append({"name": "global", "scope": "global", "path": global_md,
                    "owner": compute_owner(global_md)})
    root_md = f"{PROJECT_ROOT}/AGENTS.md"
    if os.path.isfile(root_md):
        out.append({"name": "root", "scope": "project", "path": root_md,
                    "owner": compute_owner(root_md)})
    for sub_path in SUBPROJECT_MAP:
        md = f"{PROJECT_ROOT}/{sub_path}/AGENTS.md"
        if os.path.isfile(md):
            out.append({"name": sub_path, "scope": "subproject", "path": md,
                        "owner": compute_owner(md)})
    return out


def list_plugin_commands():
    """返回 [dict]. 每项: {name, scope, path, owner}. plugin 命令无 scope."""
    ensure_plugin_skill_cache()
    out = []
    for name, path in sorted((_PLUGIN_SKILL_CACHE or {}).items()):
        out.append({
            "name": name, "scope": "plugin", "path": path,
            "owner": compute_owner(path),
        })
    return out


_TIKTOKEN_ENC = None
_TIKTOKEN_STATUS = "未初始化"


def _init_tiktoken():
    """lazy init tiktoken. cl100k_base (GPT-4 编码) 是目前离线最接近 Claude 的方案.
    失败时返回 None, 上层 fallback 到 bytes/3.5."""
    global _TIKTOKEN_ENC, _TIKTOKEN_STATUS
    if _TIKTOKEN_ENC is not None:
        return _TIKTOKEN_ENC
    try:
        import tiktoken
        _TIKTOKEN_ENC = tiktoken.get_encoding("cl100k_base")
        _TIKTOKEN_STATUS = f"tiktoken cl100k_base"
        return _TIKTOKEN_ENC
    except Exception:
        _TIKTOKEN_ENC = False
        _TIKTOKEN_STATUS = "bytes/3.5 (tiktoken 未安装)"
        return None


def estimate_tokens(text_or_bytes) -> int:
    """精确估算 Claude token 数.
    优先使用 tiktoken cl100k_base (离线最佳近似),
    未安装时 fallback 到 bytes/3.5.
    """
    enc = _init_tiktoken()
    if enc:
        if isinstance(text_or_bytes, bytes):
            text = text_or_bytes.decode("utf-8", errors="replace")
        else:
            text = text_or_bytes
        try:
            return len(enc.encode(text, disallowed_special=()))
        except Exception:
            pass
    # fallback
    if isinstance(text_or_bytes, bytes):
        n = len(text_or_bytes)
    else:
        n = len(text_or_bytes.encode("utf-8"))
    return max(1, int(n / 3.5))


# Token 计算缓存: path -> (mtime, total_tokens, sections_tokens)
_TOKEN_CACHE = {}


def list_memory_files():
    """返回 [dict]. 每项: {name, scope, path, owner}. memory scope = 'auto'."""
    if not os.path.isdir(MEMORY_DIR):
        return []
    out = []
    for f in sorted(os.listdir(MEMORY_DIR)):
        if f.endswith(".md"):
            full = os.path.join(MEMORY_DIR, f)
            out.append({
                "name": f[:-3], "scope": "auto", "path": full,
                "owner": compute_owner(full),
            })
    return out


# ============================================================
# 区块: COLD_SECTIONS 单源定义
# 新增 cold 类型: 在这里加一条 + 在 LABELS 里加 label_key (assert 会提醒)
# ============================================================
COLD_SECTIONS = [
    {
        "id": "cold_skills",
        "label_key": "cold_skills",
        "event_type": "skill_read",
        "source": list_skill_files,
        "key_fn": lambda x: (x["name"], x["scope"]),
        "last_seen_key_fn": lambda x: (x["name"], x["scope"]),
        "supports_archive": True,
        "archive_type": "skill",
    },
    {
        "id": "cold_skills_explicit",
        "label_key": "cold_skills_explicit",
        "event_type": "skill_explicit",
        "source": list_skill_files,
        "key_fn": lambda x: (x["name"], x["scope"]),
        "last_seen_key_fn": lambda x: (x["name"], x["scope"]),
        "supports_archive": True,
        "archive_type": "skill",
        "name_filter": lambda n: ":" not in n,  # 排除 plugin 命令
    },
    {
        "id": "cold_subagents",
        "label_key": "cold_subagents",
        "event_type": "subagent",
        "source": list_subagent_files,
        "key_fn": lambda x: x["name"],
        "last_seen_key_fn": lambda x: (x["name"], ""),
        "supports_archive": True,
        "archive_type": "subagent",
        "override_same_name": True,  # user 同名被 project 覆盖
    },
    {
        "id": "cold_clinerules",
        "label_key": "cold_clinerules",
        "event_type": "clinerule_read",
        "source": list_clinerules,
        "key_fn": lambda x: x["name"],
        "last_seen_key_fn": lambda x: (x["name"], "project"),
        "supports_archive": False,
    },
    {
        "id": "cold_claude_md",
        "label_key": "cold_claude_md",
        "event_type": "claude_md_read",
        "source": list_claude_mds,
        "key_fn": lambda x: x["name"],
        "last_seen_key_fn": lambda x: (x["name"], x["scope"]),
        "supports_archive": False,
    },
    {
        "id": "cold_memory",
        "label_key": "cold_memory",
        "event_type": "memory_read",
        "source": list_memory_files,
        "key_fn": lambda x: x["name"],
        "last_seen_key_fn": lambda x: (x["name"], "auto"),
        "supports_archive": False,
    },
    {
        "id": "cold_agents_md",
        "label_key": "cold_agents_md",
        "event_type": "agents_md_read",
        "source": list_agents_mds,
        "key_fn": lambda x: x["name"],
        "last_seen_key_fn": lambda x: (x["name"], x["scope"]),
        "supports_archive": False,
    },
    {
        "id": "cold_plugins",
        "label_key": "cold_plugins",
        "event_type": "skill_explicit",
        "source": list_plugin_commands,
        "key_fn": lambda x: x["name"],
        "last_seen_key_fn": lambda x: (x["name"], ""),
        "supports_archive": False,
        "name_filter": lambda n: ":" in n,  # 只看 plugin 命令
    },
]

# 启动时校验: 每个 section 的 label_key 必须在 LABELS 里有对应文案
_missing_labels = [sd["label_key"] for sd in COLD_SECTIONS if sd["label_key"] not in LABELS]
if _missing_labels:
    raise RuntimeError(f"COLD_SECTIONS: 缺少 LABELS 定义 {_missing_labels}")
del _missing_labels


# C12: 从 EVENT_TYPES schema 派生 pairable 集合 (单一真理源)
PAIRABLE_READ_TYPES = {t for t, _, p in EVENT_TYPES if p}
PAIRED_ACTION_TYPES = ("skill_explicit", "subagent")


# ============================================================
# 区块: 渲染辅助 + 路径常量
# ============================================================
# HOOKS_DIR = ~/Desktop/ai-project/hooks (从 shared/infra/core.py 回三层)
HOOKS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CSS_PATH = os.path.join(HOOKS_DIR, "shared", "static", "style.css")
JS_PATH = os.path.join(HOOKS_DIR, "shared", "static", "app.js")


# ============================================================
# 区块: 渲染辅助函数 (提到模块级以便子函数共享)
# ============================================================
def severity_cls(count: int, total: int) -> str:
    if total == 0:
        return "low"
    ratio = count / total
    if ratio >= 0.7:
        return "high"
    if ratio >= 0.3:
        return "mid"
    return "low"


def fmt_last_seen(ts: str) -> str:
    """冷藏候選的最後觸發時間. 無記錄時返回空 (因為 cold 列表本身語義自明, 顯示"從未觸發"冗餘)."""
    if not ts:
        return ""
    d = days_ago(ts)
    if d < 0:
        return ""
    if d == 0:
        return "今天"
    return f"{d} 天前"
