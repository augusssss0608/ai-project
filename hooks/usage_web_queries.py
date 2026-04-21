#!/usr/bin/env python3
"""Queries module: SQL 查詢 + 分析.
依賴 core 模組."""
import os
import sqlite3
import html
from datetime import datetime, timedelta, timezone
from usage_web_core import *
# `import *` 排除底線開頭, 顯式 import queries 需要的核心私有名
from usage_web_core import _init_tiktoken, _TOKEN_CACHE, _PLUGIN_SKILL_CACHE



# ============================================================
# 区块: SQL 查询
# ============================================================
def query_counts(conn, etype: str, days: int):
    """返回 [(name, scope, count, sample_path)] ."""
    cur = conn.execute(
        "SELECT name, COALESCE(scope,'') AS scope, COUNT(*) c, MAX(path) p "
        "FROM events WHERE type=? AND ts >= ? "
        "GROUP BY name, COALESCE(scope,'') ORDER BY c DESC",
        (etype, cutoff_ts(days)),
    )
    return cur.fetchall()


def query_last_seen(conn, etype: str):
    """返回 {(name, scope): last_seen_ts_iso} 对所有历史事件 (不限时间窗)."""
    cur = conn.execute(
        "SELECT name, COALESCE(scope,'') AS scope, MAX(ts) "
        "FROM events WHERE type=? GROUP BY name, COALESCE(scope,'')",
        (etype,),
    )
    return {(row[0], row[1]): row[2] for row in cur.fetchall()}


def query_owner_activity(conn, days: int):
    """按 owner 聚合活动数据, 用于跨项目 Today 面板.
    返回 {owner: {last_ts, event_count, recent_items: [(name, type, ts, path)]}}."""
    cur = conn.execute(
        "SELECT name, type, path, ts, scope FROM events "
        "WHERE ts >= ? ORDER BY ts DESC",
        (cutoff_ts(days),),
    )
    result = {}
    for name, etype, path, ts, scope in cur.fetchall():
        # 推导 owner
        owner = compute_owner(path) if path else ("live_app" if etype == "memory_read" else ("builtin" if etype == "subagent" else "global"))
        if owner not in result:
            result[owner] = {"last_ts": ts, "event_count": 0, "recent_items": []}
        result[owner]["event_count"] += 1
        if ts > result[owner]["last_ts"]:
            result[owner]["last_ts"] = ts
        # 只保留最近 5 项 (携带 path 以供点击打开)
        if len(result[owner]["recent_items"]) < 5:
            result[owner]["recent_items"].append((name or "", etype, ts, path or ""))
    return result


def query_subproject_health(conn, days: int):
    """子项目健康: 返回 {subproject: {last_activity, event_count, error_count, cold_count}}."""
    owner_activity = query_owner_activity(conn, days)
    error_count = 0
    err_file = f"{USER_HOME}/Desktop/ai-project/data/tracker-errors.log"
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    if os.path.isfile(err_file):
        try:
            with open(err_file) as f:
                for line in f:
                    # 格式: [2026-04-13T15:00:35Z] ...
                    if line.startswith("["):
                        ts_str = line[1:21]
                        try:
                            dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                            if dt >= recent_cutoff:
                                error_count += 1
                        except Exception:
                            pass
        except Exception:
            pass
    # 冷藏资产数: 按 owner 统计 cold 项 (需要外部传入, 这里占位)
    out = {}
    for sub_path, owner in SUBPROJECT_MAP.items():
        info = owner_activity.get(owner, {"last_ts": "", "event_count": 0, "recent_items": []})
        out[owner] = {
            "sub_path": sub_path,
            "last_ts": info["last_ts"],
            "event_count": info["event_count"],
            "error_count": error_count,  # 全局错误数(简化)
        }
    return out


def query_week_over_week(conn):
    """近 7 天 vs 前 7 天事件数对比. 返回 (this_week, last_week)."""
    now = datetime.now(timezone.utc)
    this_week_start = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    last_week_start = (now - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")
    this_week = conn.execute(
        "SELECT COUNT(*) FROM events WHERE ts >= ?", (this_week_start,)
    ).fetchone()[0]
    last_week = conn.execute(
        "SELECT COUNT(*) FROM events WHERE ts >= ? AND ts < ?",
        (last_week_start, this_week_start),
    ).fetchone()[0]
    return this_week, last_week


def query_daily_counts(conn, days: int):
    """返回最近 N 天每日事件数 [(date, count)] (缺失日补 0).
    覆盖從 cutoff 日到今日的完整日期序列, 避免時區邊界導致某日事件顯示不到."""
    cur = conn.execute(
        "SELECT substr(ts, 1, 10) AS day, COUNT(*) "
        "FROM events WHERE ts >= ? GROUP BY day ORDER BY day",
        (cutoff_ts(days),),
    )
    day_map = {row[0]: row[1] for row in cur.fetchall()}
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=max(days - 1, 1))).date()
    end_date = now.date()
    out = []
    d = start_date
    while d <= end_date:
        key = d.strftime("%Y-%m-%d")
        out.append((key, day_map.get(key, 0)))
        d += timedelta(days=1)
    return out


# ============================================================
# 区块: 数据整形 (active rows 附加 owner/path)
# ============================================================
def attach_owner_active(etype: str, rows):
    """为 active section 行数据附加 owner 和 path (可能反查).
    返回 [(name, scope, count, path, owner)] ."""
    out = []
    for name, scope, count, path in rows:
        # 反查路径 (skill_explicit / subagent 事件本身没 path)
        if not path:
            if etype == "skill_explicit":
                path = resolve_skill_path(name, scope)
            elif etype == "subagent":
                path = resolve_subagent_path(name)
        if path:
            owner = compute_owner(path)
        elif etype == "subagent":
            # 没有文件路径的 subagent = Claude Code 内建 (Explore/Plan/general-purpose 等)
            owner = "builtin"
        elif etype == "skill_explicit":
            # 没有文件的 skill_explicit = Claude Code 内建/系统 skill (如 update-config)
            owner = "builtin"
        else:
            owner = "unknown"
        out.append((name, scope, count, path or "", owner))
    return out


def build_weighted_event_counts(conn):
    """A: 时间加权 hit_count.
    近 7 天 ×3, 7-30 天 ×1, 30+ 天 ×0.3.
    返回 {name: weighted_count}."""
    now = datetime.now(timezone.utc)
    cut_7d = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cut_30d = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    weighted = {}
    # 近 7 天 x3
    for name, c in conn.execute(
        "SELECT name, COUNT(*) FROM events WHERE ts >= ? GROUP BY name", (cut_7d,)
    ).fetchall():
        weighted[name] = weighted.get(name, 0) + c * 3.0
    # 7-30 天 x1
    for name, c in conn.execute(
        "SELECT name, COUNT(*) FROM events WHERE ts >= ? AND ts < ? GROUP BY name",
        (cut_30d, cut_7d),
    ).fetchall():
        weighted[name] = weighted.get(name, 0) + c * 1.0
    # 30+ 天 x0.3
    for name, c in conn.execute(
        "SELECT name, COUNT(*) FROM events WHERE ts < ? GROUP BY name", (cut_30d,)
    ).fetchall():
        weighted[name] = weighted.get(name, 0) + c * 0.3
    return weighted


def compute_prune_score(section: dict, hit_weighted: float) -> tuple:
    """计算删减收益分 = token_score + stale_score - keep_score.
    返回 (score, bucket, token_score, stale_score, keep_score)."""
    tokens = section["tokens"]
    # token_score 0/10/20/30
    if tokens < 80:
        token_score = 0
    elif tokens < 200:
        token_score = 10
    elif tokens < 400:
        token_score = 20
    else:
        token_score = 30
    # stale_score 0/10/20/30
    if hit_weighted >= 8:
        stale_score = 0
    elif hit_weighted >= 2:
        stale_score = 10
    elif hit_weighted >= 1:
        stale_score = 20
    else:
        stale_score = 30
    # keep_score: 最小版本只用 heat_band + discipline_flag
    if hit_weighted >= 50:
        heat_band = 1.0
    elif hit_weighted >= 1:
        heat_band = 0.5
    else:
        heat_band = 0.0
    discipline_flag = 1 if section.get("has_discipline") else 0
    keep_score = 35 * heat_band + 20 * discipline_flag
    final = max(0, token_score + stale_score - keep_score)
    # 分桶
    if final >= 40:
        bucket = "prune-high"
    elif final >= 20:
        bucket = "prune-mid"
    else:
        bucket = "prune-low"
    return (final, bucket, token_score, stale_score, keep_score)


def _collect_known_resources(conn):
    """收集所有已知资源名 (skill, subagent, clinerule, memory, etc.) 用于匹配 CLAUDE.md 引用."""
    names = set()
    # skills
    for d in [f"{USER_HOME}/.claude/skills", f"{PROJECT_ROOT}/.claude/skills"]:
        if os.path.isdir(d):
            for sk in os.listdir(d):
                if not sk.startswith("."):
                    names.add(sk)
    # subagents
    for d in [f"{USER_HOME}/.claude/agents", f"{PROJECT_ROOT}/.claude/agents"]:
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".md") and not f.startswith("."):
                    names.add(f[:-3])
    # clinerules 文件名
    for root, _, files in os.walk(f"{PROJECT_ROOT}/.clinerules"):
        for f in files:
            if f.endswith(".md"):
                names.add(f[:-3])  # 去掉 .md
                names.add(f)       # 带 .md
    return names


def analyze_claude_md(path: str, known_names: set, weighted_hits: dict):
    """解析 CLAUDE.md 按 ## 和 ### 分节, 计算时间加权热度 + prune_score.
    使用 tiktoken 精确计算 token (失败时 fallback bytes/3.5).
    结果按 mtime 缓存."""
    try:
        mtime = os.path.getmtime(path)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None

    cached = _TOKEN_CACHE.get(path)
    lines = content.split("\n")
    total_bytes = len(content.encode("utf-8"))
    if cached and cached[0] == mtime:
        total_tokens = cached[1]
    else:
        total_tokens = estimate_tokens(content)

    # C: 按 ## 和 ### 双层分节
    import re
    sections = []  # (level, heading, start_line, lines)
    current_level = 0
    current_heading = "(preamble)"
    current_start = 1
    current_lines = []
    for idx, line in enumerate(lines, 1):
        m2 = re.match(r"^##\s+(.+)$", line)
        m3 = re.match(r"^###\s+(.+)$", line)
        if m2 and not line.startswith("###"):
            if current_lines:
                sections.append((current_level, current_heading, current_start, current_lines))
            current_level = 2
            current_heading = m2.group(1).strip()
            current_start = idx
            current_lines = [line]
        elif m3:
            if current_lines:
                sections.append((current_level, current_heading, current_start, current_lines))
            current_level = 3
            current_heading = m3.group(1).strip()
            current_start = idx
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_level, current_heading, current_start, current_lines))

    # 对每节评分
    cached_section_tokens = (cached[2] if cached and cached[0] == mtime else None)
    out_sections = []
    section_tokens_for_cache = []
    for sec_idx, (level, heading, start_line, sec_lines) in enumerate(sections):
        text = "\n".join(sec_lines)
        sec_bytes = len(text.encode("utf-8"))
        if cached_section_tokens and sec_idx < len(cached_section_tokens):
            sec_tokens = cached_section_tokens[sec_idx]
        else:
            sec_tokens = estimate_tokens(text)
        section_tokens_for_cache.append(sec_tokens)
        # 找匹配的资源名
        mentioned = set()
        for name in known_names:
            if len(name) < 4:
                continue
            if name in text:
                mentioned.add(name)
        # A: 用加权 hit_count
        hit_weighted = sum(weighted_hits.get(n, 0) for n in mentioned)
        # 纪律性关键词
        has_discipline = any(
            kw in text for kw in ["禁止", "必须", "不得", "警告", "不要", "绝不", "MUST", "NEVER", "REQUIRED"]
        )
        # 热度分桶 (基于加权 hit)
        if has_discipline and hit_weighted < 10:
            heat = "warn"
        elif hit_weighted >= 50:
            heat = "hot"
        elif hit_weighted >= 1:
            heat = "warm"
        else:
            heat = "cold"
        # 构造 section 字典 (preview = 截斷的段落內文, tooltip 用)
        body_text = text.strip()
        if len(body_text) > 600:
            body_text = body_text[:600] + "…"
        sec_dict = {
            "level": level,
            "heading": heading,
            "line_start": start_line,
            "line_count": len(sec_lines),
            "bytes": sec_bytes,
            "tokens": sec_tokens,
            "heat": heat,
            "hit_weighted": round(hit_weighted, 1),
            "mentioned_count": len(mentioned),
            "has_discipline": has_discipline,
            "preview": body_text,
        }
        # 计算 prune_score
        p_score, bucket, ts_s, st_s, k_s = compute_prune_score(sec_dict, hit_weighted)
        sec_dict.update({
            "prune_score": p_score,
            "prune_bucket": bucket,
            "token_score": ts_s,
            "stale_score": st_s,
            "keep_score": k_s,
        })
        out_sections.append(sec_dict)

    _TOKEN_CACHE[path] = (mtime, total_tokens, section_tokens_for_cache)

    return {
        "path": path,
        "total_bytes": total_bytes,
        "total_tokens": total_tokens,
        "sections": out_sections,
    }


def compute_cold_items(section_def: dict, active_data: dict):
    """根据 COLD_SECTIONS 定义计算该 section 的 cold items.

    返回 (cold_items, universe, overridden_names):
      - cold_items: [dict] 冷藏项列表 (已禁用的也算冷)
      - universe: [dict] 源文件全集
      - overridden_names: set[str] 被同名 project 覆盖的 user 对象名 (仅 override_same_name=True 时非空)
    """
    source_fn = section_def["source"]
    universe = source_fn()
    etype = section_def["event_type"]
    key_fn = section_def["key_fn"]
    name_filter = section_def.get("name_filter")  # None 或 lambda(name) -> bool

    # name_filter 同时过滤 universe 和 active (保证 universe_count 和 cold 检测一致)
    if name_filter:
        universe = [item for item in universe if name_filter(item["name"])]

    # 已触发的 key 集合
    used_keys = set()
    for name, scope, _count, _path, _owner in active_data.get(etype, []):
        if name_filter and not name_filter(name):
            continue
        used_keys.add(key_fn({"name": name, "scope": scope or ""}))

    # 子 agent 同名 project 覆盖 user
    overridden_names = set()
    if section_def.get("override_same_name"):
        project_names = {i["name"] for i in universe if i["scope"] == "project"}
        user_names = {i["name"] for i in universe if i["scope"] == "user"}
        overridden_names = user_names & project_names

    # 计算 cold: 已禁用 OR 未触发, 排除被覆盖的 user 版本
    cold = []
    for item in universe:
        is_disabled = item.get("disabled", False)
        if not is_disabled and key_fn(item) in used_keys:
            continue
        if item["scope"] == "user" and item["name"] in overridden_names:
            continue
        cold.append(item)
    return cold, universe, overridden_names


def query_sessions_count(conn, etype: str, days: int):
    """C11: 统计每个对象 30 天内唯一 session 数 (sessions_30d 衍生指标)."""
    cur = conn.execute(
        "SELECT name, COALESCE(scope,'') AS scope, COUNT(DISTINCT session) "
        "FROM events WHERE type=? AND ts >= ? AND session != '' "
        "GROUP BY name, COALESCE(scope,'')",
        (etype, cutoff_ts(days)),
    )
    return {(row[0], row[1]): row[2] for row in cur.fetchall()}


def query_paired_count(conn, etype: str, days: int):
    """C12: 统计同 session 内 5 分钟窗口内能配对到动作事件的次数 (paired_30d).

    SB3 修复: 返回 (paired, pairable_total)，分母只算 session != '' 的事件，
    避免无 session 事件导致配对率 over-count 偏低.
    返回 {(name, scope): (paired, pairable_total)}.
    """
    if etype not in PAIRABLE_READ_TYPES:
        return {}
    cur = conn.execute(
        """
        SELECT
          name,
          COALESCE(scope,'') AS scope,
          SUM(CASE WHEN paired=1 THEN 1 ELSE 0 END) AS paired_count,
          COUNT(*) AS pairable_total
        FROM (
          SELECT
            e1.name,
            e1.scope,
            CASE WHEN EXISTS (
              SELECT 1 FROM events e2
              WHERE e2.session = e1.session
                AND e2.type IN ('skill_explicit', 'subagent')
                AND datetime(e2.ts) BETWEEN datetime(e1.ts) AND datetime(e1.ts, '+5 minutes')
            ) THEN 1 ELSE 0 END AS paired
          FROM events e1
          WHERE e1.type = ?
            AND e1.ts >= ?
            AND e1.session != ''
        )
        GROUP BY name, COALESCE(scope,'')
        """,
        (etype, cutoff_ts(days)),
    )
    return {(row[0], row[1]): (row[2], row[3]) for row in cur.fetchall()}


# ============================================================
# 区块: 卡片背面数据查询 (Phase 1 翻面卡片)
# ============================================================
def query_etype_aggregate(conn, etype: str, days: int, owner_filter: str = "") -> dict:
    """聚合一個事件 type 的背面數據. owner_filter 非空時只算該 owner 事件."""
    out = {
        "daily": [],
        "last_ts": "",
        "day_coverage": (0, days),
        "session_coverage": (0, 0),
        "owner_dist": {},
        "paired_total": 0,
        "pairable_total": 0,
        "token_estimate": 0,
        "token_breakdown": "",
    }
    cutoff = cutoff_ts(days)

    def _owner_match(path: str) -> bool:
        if not owner_filter:
            return True
        own = compute_owner(path) if path else (
            "live_app" if etype == "memory_read"
            else ("builtin" if etype == "subagent" else "global")
        )
        return own == owner_filter

    # 每日觸發數 (需要按 owner 過濾, 改為遍歷)
    cur = conn.execute(
        "SELECT substr(ts,1,10), path FROM events WHERE type=? AND ts>=?",
        (etype, cutoff),
    )
    day_map = {}
    for day, path in cur.fetchall():
        if not _owner_match(path):
            continue
        day_map[day] = day_map.get(day, 0) + 1
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=max(days - 1, 1))).date()
    end_date = now.date()
    d = start_date
    while d <= end_date:
        out["daily"].append((d.strftime("%Y-%m-%d"), day_map.get(d.strftime("%Y-%m-%d"), 0)))
        d += timedelta(days=1)
    # 最後觸發時間 + 覆蓋率 + owner 分布 + 配對率 + token: 全部需要按 owner 過濾, 統一遍歷一次
    cur = conn.execute(
        "SELECT name, COALESCE(scope,''), path, ts, session FROM events WHERE type=? AND ts>=?",
        (etype, cutoff),
    )
    last_ts = ""
    days_set = set()
    sess_set = set()
    sess_total_set = set()
    dist = {}
    name_path_count = {}  # (name, path) -> count, 用於 token 估算
    for name, scope, path, ts, session in cur.fetchall():
        if not _owner_match(path):
            continue
        if ts > last_ts:
            last_ts = ts
        days_set.add(ts[:10])
        if session:
            sess_set.add(session)
        own = compute_owner(path) if path else (
            "live_app" if etype == "memory_read"
            else ("builtin" if etype == "subagent" else "global")
        )
        dist[own] = dist.get(own, 0) + 1
        key = (name, path or "")
        name_path_count[key] = name_path_count.get(key, 0) + 1
    out["last_ts"] = last_ts
    out["day_coverage"] = (len(days_set), days)
    # session_total 是整個窗口所有 type 的 distinct session (作分母)
    cur = conn.execute(
        "SELECT DISTINCT session FROM events WHERE ts>=? AND session != ''",
        (cutoff,),
    )
    sess_total_set = {r[0] for r in cur.fetchall()}
    out["session_coverage"] = (len(sess_set), len(sess_total_set))
    out["owner_dist"] = dist
    # 配對率 (按 owner 過濾)
    if etype in PAIRABLE_READ_TYPES:
        paired_map = query_paired_count(conn, etype, days)
        # paired_map key 是 (name, scope), 沒有 path 信息. 配對率 owner 過濾不精確, 先用全局
        for (n, s), (p, pt) in paired_map.items():
            out["paired_total"] += p
            out["pairable_total"] += pt
    # token 估算: 已按 owner 過濾的 name_path_count
    total_tok = 0
    files_counted = 0
    for (name, path), count in name_path_count.items():
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read(20000)
            tok = estimate_tokens(text)
            total_tok += tok * count
            files_counted += 1
        except Exception:
            pass
    out["token_estimate"] = total_tok
    suffix = f" · owner={owner_filter}" if owner_filter else ""
    out["token_breakdown"] = f"{files_counted} 个文件, 含触发次数加权{suffix}"
    return out


def query_cold_progress(section_def: dict, universe: list, cold_items: list) -> dict:
    """裝飾品候選卡的背面數據: 已禁用進度 + 統計."""
    total = len(universe)
    disabled = sum(1 for i in cold_items if i.get("disabled"))
    cold_active = sum(1 for i in cold_items if not i.get("disabled"))
    return {
        "total": total,
        "cold_count": len(cold_items),
        "disabled": disabled,
        "cold_active": cold_active,
        "active_used": total - len(cold_items),
    }


def query_hero_aggregates(conn, days: int) -> dict:
    """Hero 4 卡背面數據."""
    cutoff = cutoff_ts(days)
    out = {}
    # 1. 周期對比 (本窗口 vs 前一個同長度窗口)
    cur = conn.execute("SELECT COUNT(*) FROM events WHERE ts >= ?", (cutoff,))
    cur_count = cur.fetchone()[0] or 0
    prev_cutoff_start = (datetime.now(timezone.utc) - timedelta(days=days * 2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur = conn.execute(
        "SELECT COUNT(*) FROM events WHERE ts >= ? AND ts < ?",
        (prev_cutoff_start, cutoff),
    )
    prev_count = cur.fetchone()[0] or 0
    pct_change = ((cur_count - prev_count) / max(prev_count, 1)) * 100 if prev_count > 0 else 0
    out["period"] = {"current": cur_count, "previous": prev_count, "pct_change": pct_change}
    # 2. 事件按 type 拆分
    cur = conn.execute(
        "SELECT type, COUNT(*) FROM events WHERE ts >= ? GROUP BY type ORDER BY 2 DESC",
        (cutoff,),
    )
    out["type_breakdown"] = list(cur.fetchall())
    # 3. 最近 session 列表 + 平均每會話事件數
    cur = conn.execute(
        "SELECT session, COUNT(*) AS n, MAX(ts) AS last_ts FROM events "
        "WHERE ts >= ? AND session != '' GROUP BY session ORDER BY last_ts DESC LIMIT 5",
        (cutoff,),
    )
    sessions = [{"id": r[0], "events": r[1], "ts": r[2]} for r in cur.fetchall()]
    cur = conn.execute(
        "SELECT COUNT(DISTINCT session), COUNT(*) FROM events "
        "WHERE ts >= ? AND session != ''",
        (cutoff,),
    )
    sess_count, total_events = cur.fetchone()
    avg_per_sess = (total_events / sess_count) if sess_count else 0
    out["sessions"] = {
        "recent": sessions,
        "avg_per_session": avg_per_sess,
    }
    # 4. 累計: db 年齡 + 按月分布
    cur = conn.execute("SELECT MIN(ts), COUNT(*) FROM events")
    first_ts, all_count = cur.fetchone()
    db_age_days = 0
    if first_ts:
        db_age_days = max(0, (datetime.now(timezone.utc) - datetime.strptime(first_ts.rstrip("Z"), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)).days)
    cur = conn.execute(
        "SELECT substr(ts,1,7) AS mon, COUNT(*) FROM events GROUP BY mon ORDER BY mon DESC LIMIT 12"
    )
    monthly_map = {r[0]: r[1] for r in cur.fetchall()}
    # 補齊 12 個月 (缺的月份顯示為 0, 避免單根長條看起來怪異)
    monthly = []
    cur_dt = datetime.now(timezone.utc).replace(day=1)
    for i in range(11, -1, -1):
        # 倒推 i 個月
        year = cur_dt.year
        month = cur_dt.month - i
        while month <= 0:
            month += 12
            year -= 1
        key = f"{year:04d}-{month:02d}"
        monthly.append((key, monthly_map.get(key, 0)))
    out["all_time"] = {
        "first_ts": first_ts or "",
        "db_age_days": db_age_days,
        "total": all_count or 0,
        "monthly": monthly,
    }
    return out


def query_owner_back(conn, owner: str, days: int) -> dict:
    """Today 卡片背面 (per owner) 數據."""
    cutoff = cutoff_ts(days)
    cur = conn.execute(
        "SELECT path, type, ts, session FROM events WHERE ts >= ? ORDER BY ts DESC",
        (cutoff,),
    )
    rows = []
    for path, etype, ts, session in cur.fetchall():
        own = compute_owner(path) if path else (
            "live_app" if etype == "memory_read"
            else ("builtin" if etype == "subagent" else "global")
        )
        if own == owner:
            rows.append((etype, ts, session))
    type_counts = {}
    sessions = set()
    last_ts = ""
    for etype, ts, session in rows:
        type_counts[etype] = type_counts.get(etype, 0) + 1
        if session:
            sessions.add(session)
        if ts > last_ts:
            last_ts = ts
    # 每日趨勢
    days_map = {}
    for _, ts, _ in rows:
        d = ts[:10]
        days_map[d] = days_map.get(d, 0) + 1
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=max(days - 1, 1))).date()
    end_date = now.date()
    daily = []
    d = start_date
    while d <= end_date:
        key = d.strftime("%Y-%m-%d")
        daily.append((key, days_map.get(key, 0)))
        d += timedelta(days=1)
    return {
        "type_counts": type_counts,
        "session_count": len(sessions),
        "last_session": next((r[2] for r in rows if r[2]), ""),
        "last_ts": last_ts,
        "daily": daily,
    }


def query_health_back(conn, owner: str, days: int) -> dict:
    """Health 卡片背面 (per subproject) 數據."""
    cutoff = cutoff_ts(days)
    # 24h 每小時觸發數
    cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur = conn.execute(
        "SELECT substr(ts,1,13), path FROM events WHERE ts >= ?",
        (cutoff_24h,),
    )
    hourly_map = {}
    for hour, path in cur.fetchall():
        own = compute_owner(path) if path else "global"
        if own == owner:
            hourly_map[hour] = hourly_map.get(hour, 0) + 1
    now = datetime.now(timezone.utc)
    hourly = []
    for i in range(23, -1, -1):
        hour_key = (now - timedelta(hours=i)).strftime("%Y-%m-%dT%H")
        hourly.append((hour_key, hourly_map.get(hour_key, 0)))
    # 錯誤日誌讀取
    err_file = f"{USER_HOME}/Desktop/ai-project/data/tracker-errors.log"
    errors = []
    if os.path.isfile(err_file):
        try:
            with open(err_file, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-50:]
            errors = [l.strip() for l in lines if l.strip()][-5:]
        except Exception:
            pass
    # 空窗時長
    cur = conn.execute(
        "SELECT MAX(ts) FROM events WHERE ts >= ?",
        (cutoff,),
    )
    last_any = cur.fetchone()[0] or ""
    gap_str = ""
    if last_any:
        try:
            last_dt = datetime.strptime(last_any.rstrip("Z"), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - last_dt
            if delta.days > 0:
                gap_str = f"{delta.days} 天"
            elif delta.seconds >= 3600:
                gap_str = f"{delta.seconds // 3600} 小时"
            else:
                gap_str = f"{delta.seconds // 60} 分钟"
        except Exception:
            gap_str = "—"
    return {
        "hourly": hourly,
        "errors": errors,
        "gap": gap_str,
    }


def query_claude_md_aggregate(analysis: dict) -> dict:
    """CLAUDE.md 卡的背面數據: 文件級總覽 + 可刪減清單."""
    sections = analysis.get("sections", [])
    total_tok = analysis.get("total_tokens", 0)
    high_n = sum(1 for s in sections if s.get("prune_bucket") == "prune-high")
    mid_n = sum(1 for s in sections if s.get("prune_bucket") == "prune-mid")
    high_tok = sum(s["tokens"] for s in sections if s.get("prune_bucket") == "prune-high")
    mid_tok = sum(s["tokens"] for s in sections if s.get("prune_bucket") == "prune-mid")
    discipline = sum(1 for s in sections if s.get("has_discipline"))
    return {
        "total_tok": total_tok,
        "section_count": len(sections),
        "high_n": high_n,
        "mid_n": mid_n,
        "high_tok": high_tok,
        "mid_tok": mid_tok,
        "discipline": discipline,
        "saveable_pct": int(100 * high_tok / max(total_tok, 1)),
    }
