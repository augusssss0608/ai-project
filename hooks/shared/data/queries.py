#!/usr/bin/env python3
"""Queries module: SQL 查詢 + 分析.
依賴 core 模組."""
import os
from datetime import datetime, timedelta, timezone
from shared.infra.core import *
from shared.infra.core import _TOKEN_CACHE  # `import *` 不带 _



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
    返回 {owner: {last_ts, event_count, recent_items: [(name, type, ts, path)]}}.

    user_prompt 是会话级元数据（只在路由 tab 的 session 展开里显示），
    不算"工具使用活动"，从 Today 排除。"""
    cur = conn.execute(
        "SELECT name, type, path, ts, scope FROM events "
        "WHERE ts >= ? AND type != 'user_prompt' ORDER BY ts DESC",
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


def query_recent_events(conn, days: int, limit: int = 30):
    """跨 owner 混合的最近 N 条事件，按时间倒序。
    返回 [{ts, owner, type, name, path}]，用于 Today · Event Stream。

    user_prompt 排除（同 Today 其他面板）。"""
    cur = conn.execute(
        "SELECT ts, name, type, path FROM events "
        "WHERE ts >= ? AND type != 'user_prompt' "
        "ORDER BY ts DESC LIMIT ?",
        (cutoff_ts(days), limit),
    )
    out = []
    for ts, name, etype, path in cur.fetchall():
        owner = compute_owner(path) if path else (
            "live_app" if etype == "memory_read"
            else ("builtin" if etype == "subagent" else "global")
        )
        out.append({
            "ts": ts,
            "owner": owner,
            "type": etype,
            "name": name or "",
            "path": path or "",
        })
    return out


def query_owner_dailies(conn, days: int) -> dict:
    """每个 owner 的 daily 计数序列，用于 Owner Bay sparkline。
    返回 {owner: [(day, count), ...]}（覆盖 cutoff 到今日完整日期序列）。"""
    cur = conn.execute(
        "SELECT substr(ts, 1, 10) AS day, type, path, COUNT(*) "
        "FROM events WHERE ts >= ? AND type != 'user_prompt' "
        "GROUP BY day, type, path",
        (cutoff_ts(days),),
    )
    raw = {}  # {owner: {day: count}}
    for day, etype, path, c in cur.fetchall():
        owner = compute_owner(path) if path else (
            "live_app" if etype == "memory_read"
            else ("builtin" if etype == "subagent" else "global")
        )
        raw.setdefault(owner, {})
        raw[owner][day] = raw[owner].get(day, 0) + c

    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=max(days - 1, 1))).date()
    end_date = now.date()
    out = {}
    for owner, day_map in raw.items():
        series = []
        d = start_date
        while d <= end_date:
            key = d.strftime("%Y-%m-%d")
            series.append((key, day_map.get(key, 0)))
            d += timedelta(days=1)
        out[owner] = series
    return out


def query_owner_session_counts(conn, days: int) -> dict:
    """每个 owner 的 session_count，用于 Owner Bay。
    返回 {owner: int}。"""
    cur = conn.execute(
        "SELECT path, type, session FROM events "
        "WHERE ts >= ? AND type != 'user_prompt' AND session != ''",
        (cutoff_ts(days),),
    )
    seen = {}  # {owner: set(session)}
    for path, etype, session in cur.fetchall():
        owner = compute_owner(path) if path else (
            "live_app" if etype == "memory_read"
            else ("builtin" if etype == "subagent" else "global")
        )
        seen.setdefault(owner, set()).add(session)
    return {o: len(s) for o, s in seen.items()}


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
            owner = "other"
        out.append((name, scope, count, path or "", owner))
    return out


def build_weighted_event_counts(conn):
    """A: 时间加权 hit_count.
    近 7 天 ×3, 7-30 天 ×1, 30+ 天 ×0.3.
    返回 {name: weighted_count}.

    user_prompt.name 是 prompt 前 200 字内容，不是资源名，
    不能进资源热度统计，否则 CLAUDE.md 热度分析会把提问文本当成 hit。"""
    now = datetime.now(timezone.utc)
    cut_7d = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cut_30d = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    weighted = {}
    # 近 7 天 x3
    for name, c in conn.execute(
        "SELECT name, COUNT(*) FROM events WHERE ts >= ? AND type != 'user_prompt' GROUP BY name", (cut_7d,)
    ).fetchall():
        weighted[name] = weighted.get(name, 0) + c * 3.0
    # 7-30 天 x1
    for name, c in conn.execute(
        "SELECT name, COUNT(*) FROM events WHERE ts >= ? AND ts < ? AND type != 'user_prompt' GROUP BY name",
        (cut_30d, cut_7d),
    ).fetchall():
        weighted[name] = weighted.get(name, 0) + c * 1.0
    # 30+ 天 x0.3
    for name, c in conn.execute(
        "SELECT name, COUNT(*) FROM events WHERE ts < ? AND type != 'user_prompt' GROUP BY name", (cut_30d,)
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
    # .claude/docs 文件名（旧 .clinerules 已迁移到这里）
    for root, _, files in os.walk(f"{PROJECT_ROOT}/.claude/docs"):
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
    """Hero metric strip 数据: avg/sess + 与前 N 天对比."""
    cutoff = cutoff_ts(days)
    out = {}
    # 1. avg / session
    cur = conn.execute(
        "SELECT COUNT(DISTINCT session), COUNT(*) FROM events "
        "WHERE ts >= ? AND session != ''",
        (cutoff,),
    )
    sess_count, total_events = cur.fetchone()
    out["avg_per_session"] = (total_events / sess_count) if sess_count else 0
    # 2. 与前一个同长度窗口对比
    cur = conn.execute("SELECT COUNT(*) FROM events WHERE ts >= ?", (cutoff,))
    cur_count = cur.fetchone()[0] or 0
    prev_cutoff_start = (datetime.now(timezone.utc) - timedelta(days=days * 2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur = conn.execute(
        "SELECT COUNT(*) FROM events WHERE ts >= ? AND ts < ?",
        (prev_cutoff_start, cutoff),
    )
    prev_count = cur.fetchone()[0] or 0
    if prev_count > 0:
        pct_change = ((cur_count - prev_count) / prev_count) * 100
    elif cur_count > 0:
        pct_change = None  # 前期无数据
    else:
        pct_change = 0
    out["period"] = {"current": cur_count, "previous": prev_count, "pct_change": pct_change}
    return out


def query_owner_back(conn, owner: str, days: int) -> dict:
    """Today 卡片背面 (per owner) 數據.

    user_prompt 排除：会话级元数据，不算工具使用活动。"""
    cutoff = cutoff_ts(days)
    cur = conn.execute(
        "SELECT path, type, ts, session FROM events "
        "WHERE ts >= ? AND type != 'user_prompt' ORDER BY ts DESC",
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


# ============================================================
# 区块: 工作区健康（Phase 3.1）
# ============================================================
import json as _json
from collections import deque as _deque

_TRACKER_ERRORS_LOG = os.path.expanduser("~/Desktop/ai-project/data/tracker-errors.log")
_LINT_STATUS_FILE = os.path.expanduser("~/Desktop/ai-project/data/lint-status.json")


def _read_tracker_errors_summary():
    """读 tracker-errors.log，返回 {total_lines, recent_24h, recent_7d, last_20_lines, mtime}"""
    out = {
        "total_lines": 0,
        "recent_24h": 0,
        "recent_7d": 0,
        "last_20_lines": [],
        "mtime": None,
        "exists": False,
    }
    if not os.path.isfile(_TRACKER_ERRORS_LOG):
        return out
    out["exists"] = True
    try:
        out["mtime"] = os.path.getmtime(_TRACKER_ERRORS_LOG)
    except OSError:
        pass
    cutoff_24h = cutoff_ts(1)
    cutoff_7d = cutoff_ts(7)
    last_lines = _deque(maxlen=20)
    total = 0
    r24 = 0
    r7d = 0
    try:
        with open(_TRACKER_ERRORS_LOG, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                total += 1
                last_lines.append(line)
                # 行格式：[YYYY-MM-DDTHH:MM:SSZ] reason ...
                if line.startswith("[") and len(line) >= 22:
                    ts = line[1:21]  # YYYY-MM-DDTHH:MM:SSZ
                    if ts >= cutoff_24h:
                        r24 += 1
                    if ts >= cutoff_7d:
                        r7d += 1
    except OSError:
        pass
    out["total_lines"] = total
    out["recent_24h"] = r24
    out["recent_7d"] = r7d
    out["last_20_lines"] = list(last_lines)
    return out


def query_collection_health(conn) -> dict:
    """工作区数据采集健康摘要（Phase 3.1 健康灯使用）

    返回字段：
      status: ok | warn | error | stale
      events_24h, events_7d, total_events, last_event_at
      empty_session_pct_24h
      per_type_last_seen: [{type, label, last_seen}]
      errors: tracker-errors.log 摘要
    """
    cutoff_24h = cutoff_ts(1)
    cutoff_7d = cutoff_ts(7)

    db_readable = True
    events_24h = 0
    events_7d = 0
    total_events = 0
    last_event_at = None
    empty_24h = 0
    last_seen_map = {}

    try:
        row = conn.execute(
            "SELECT COUNT(*), SUM(CASE WHEN COALESCE(session,'')='' THEN 1 ELSE 0 END), MAX(ts) "
            "FROM events WHERE ts >= ?",
            (cutoff_24h,),
        ).fetchone()
        events_24h = row[0] or 0
        empty_24h = row[1] or 0
        # last_event_at: 用 24h 内 max；不行再扩
        last_event_at = row[2]

        row7 = conn.execute(
            "SELECT COUNT(*) FROM events WHERE ts >= ?", (cutoff_7d,),
        ).fetchone()
        events_7d = row7[0] or 0

        rowall = conn.execute(
            "SELECT COUNT(*), MAX(ts) FROM events"
        ).fetchone()
        total_events = rowall[0] or 0
        if not last_event_at:
            last_event_at = rowall[1]

        for etype, lts in conn.execute(
            "SELECT type, MAX(ts) FROM events GROUP BY type"
        ).fetchall():
            last_seen_map[etype] = lts
    except Exception:
        db_readable = False

    per_type = [
        {"type": etype, "label": label, "last_seen": last_seen_map.get(etype)}
        for etype, label, _pairable in EVENT_TYPES
    ]

    empty_pct_24h = (100.0 * empty_24h / events_24h) if events_24h > 0 else 0.0

    errors = _read_tracker_errors_summary()

    # 状态判定
    status = _derive_collection_status(
        db_readable=db_readable,
        total_events=total_events,
        events_24h=events_24h,
        events_7d=events_7d,
        last_event_at=last_event_at,
        empty_pct_24h=empty_pct_24h,
        recent_errors_24h=errors["recent_24h"],
        recent_errors_7d=errors["recent_7d"],
    )

    return {
        "status": status,
        "events_24h": events_24h,
        "events_7d": events_7d,
        "total_events": total_events,
        "last_event_at": last_event_at,
        "empty_session_count_24h": empty_24h,
        "empty_session_pct_24h": empty_pct_24h,
        "per_type_last_seen": per_type,
        "errors": errors,
    }


def _derive_collection_status(*, db_readable, total_events, events_24h, events_7d,
                               last_event_at, empty_pct_24h,
                               recent_errors_24h, recent_errors_7d) -> str:
    if not db_readable:
        return "error"
    if total_events == 0 or not last_event_at:
        return "stale"
    if events_7d == 0:
        return "error"
    if recent_errors_24h >= 10 or recent_errors_7d >= 50:
        return "error"
    if events_24h == 0:
        return "warn"
    if recent_errors_7d > 0:
        return "warn"
    if empty_pct_24h > 0:
        return "warn"
    return "ok"


def query_lint_status() -> dict | None:
    """读 lint-status.json，文件不存在返回 None"""
    if not os.path.isfile(_LINT_STATUS_FILE):
        return None
    try:
        with open(_LINT_STATUS_FILE, "r", encoding="utf-8") as f:
            return _json.load(f)
    except (OSError, _json.JSONDecodeError):
        return None


def derive_lint_status(lint_json) -> str:
    """从 lint-status.json 派生 ok/warn/error/stale 状态。
    pending 不影响总状态（pending 是 Phase 2.5 占位，不是问题）"""
    if lint_json is None:
        return "stale"
    if lint_json.get("error"):
        return "error"
    checks = lint_json.get("checks") or []
    statuses = [c.get("status") for c in checks]

    if "fail" in statuses:
        return "error"

    # last_run 缺失或解析失败视为 stale（防御性，避免老/坏 schema 误判 ok）
    last_run_iso = lint_json.get("last_run")
    if not last_run_iso:
        return "stale"
    try:
        last_run = datetime.strptime(last_run_iso.rstrip("Z"), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return "stale"
    if datetime.now(timezone.utc) - last_run > timedelta(days=7):
        return "stale"

    if lint_json.get("stale") is True:
        return "stale"

    if any(s == "warn" for s in statuses):
        return "warn"

    return "ok"


def count_lint_issues(lint_json) -> dict:
    """统计 lint 各类问题数量，用于 chip 显示"""
    out = {"fail": 0, "warn": 0, "pending": 0, "pass": 0, "skip": 0, "error": 0}
    if not lint_json:
        return out
    for c in lint_json.get("checks") or []:
        st = c.get("status")
        if st in out:
            out[st] += 1
    return out


# ============================================================
# 区块: Skill 触发漏斗（Phase 3.2）
# ============================================================
SKILL_FUNNEL_READ_ONLY_MIN = 5  # read 次数 >= 这个值才判 read-only 异常


def build_skill_funnel_rows(active_data, sessions_maps, paired_maps,
                             cold_data_by_id, last_seen_maps):
    """聚合所有 skill 的 read + explicit + sessions + paired + last_seen + status

    复用现有数据，不需要新 SQL。
    返回 [{name, scope, owner, path, read, explicit, sessions, paired_rate, last_seen, status, disabled}]
    """
    # active 数据：[(name, scope, count, path, owner)]
    read_rows = {
        ((r[0] or ""), (r[1] or "")): (r[2], r[3] or "", r[4] or "other")
        for r in active_data.get("skill_read", [])
    }
    explicit_rows = {
        ((r[0] or ""), (r[1] or "")): (r[2], r[3] or "", r[4] or "other")
        for r in active_data.get("skill_explicit", [])
        if ":" not in (r[0] or "")  # 排除 plugin:cmd
    }

    universe = {}
    for key, (_count, path, owner) in read_rows.items():
        universe.setdefault(key, {})
        universe[key]["path"] = path or universe[key].get("path", "")
        universe[key]["owner"] = owner or universe[key].get("owner", "other")
    for key, (_count, path, owner) in explicit_rows.items():
        universe.setdefault(key, {})
        universe[key]["path"] = path or universe[key].get("path", "")
        universe[key]["owner"] = owner or universe[key].get("owner", "other")

    # cold 数据并入 universe（用 cold_skills + cold_skills_explicit）
    for section_id in ("cold_skills", "cold_skills_explicit"):
        data = cold_data_by_id.get(section_id, {})
        for item in data.get("cold", []) or []:
            name = item.get("name", "")
            scope = item.get("scope", "") or ""
            if ":" in name:  # plugin cmd 排除
                continue
            key = (name, scope)
            universe.setdefault(key, {})
            universe[key].setdefault("path", item.get("path", ""))
            universe[key].setdefault("owner", item.get("owner", "other"))
            if item.get("disabled"):
                universe[key]["disabled"] = True

    read_sessions = sessions_maps.get("skill_read", {})
    explicit_sessions = sessions_maps.get("skill_explicit", {})
    paired_map = paired_maps.get("skill_read", {})
    last_read = last_seen_maps.get("skill_read", {})
    last_explicit = last_seen_maps.get("skill_explicit", {})

    rows = []
    for key, meta in universe.items():
        read_count = read_rows.get(key, (0, "", ""))[0]
        explicit_count = explicit_rows.get(key, (0, "", ""))[0]
        sessions = max(read_sessions.get(key, 0), explicit_sessions.get(key, 0))
        paired, pairable_total = paired_map.get(key, (0, 0))
        paired_rate = (paired / pairable_total) if pairable_total else None
        last_seen = max(
            last_read.get(key, "") or "",
            last_explicit.get(key, "") or "",
        ) or None

        # 状态判定（4 种）
        if read_count == 0 and explicit_count == 0:
            status = "cold"
        elif explicit_count >= 1 and read_count == 0:
            status = "explicit-only"
        elif read_count >= 1 and explicit_count == 0:
            # 任何 "读了但没显式调用" 都归 read-only（不再用 N1 阈值）
            # 让 paired 严格表示 "read>=1 且 explicit>=1"
            status = "read-only"
        else:
            status = "paired"

        rows.append({
            "name": key[0],
            "scope": key[1],
            "owner": meta.get("owner", "other"),
            "path": meta.get("path", ""),
            "read": read_count,
            "explicit": explicit_count,
            "sessions": sessions,
            "paired_rate": paired_rate,
            "paired": paired,
            "pairable_total": pairable_total,
            "last_seen": last_seen,
            "status": status,
            "disabled": bool(meta.get("disabled", False)),
        })

    # 排序：异常优先 + 同状态按最近触发倒序（用 stable sort 两步）
    severity = {
        "explicit-only": 0,
        "read-only": 1,
        "cold": 2,
        "paired": 3,
    }
    # 第一步：按 last_seen 字符串倒序（ISO 格式可直接字典序比，最近的在前；空串排最后）
    # cold 状态希望最久未触发优先，所以正序；其它倒序——分两组处理
    def _last_seen_key(r):
        ls = r.get("last_seen") or ""
        if r["status"] == "cold":
            # cold 内：从未触发（空串）和最久优先 → 空串映射到 "0"，正序
            return ls or "0"
        else:
            # 其它：最近触发优先 → 字符串本身，配合 reverse 倒序
            return ls
    # 先按时间排（活跃组倒序，cold 组正序），再按 severity 稳定排序
    rows.sort(key=lambda r: _last_seen_key(r), reverse=True)
    # 把 cold 行重排为正序：先 sort 整体倒序后，cold 子集自然变成"近的在前"，需要单独翻转
    cold_rows = [r for r in rows if r["status"] == "cold"]
    other_rows = [r for r in rows if r["status"] != "cold"]
    cold_rows.reverse()  # 倒序 → cold 内"最久未触发优先"
    rows = other_rows + cold_rows
    rows.sort(key=lambda r: severity.get(r["status"], 9))  # 稳定排序按 severity
    return rows


def funnel_status_counts(rows: list) -> dict:
    out = {"paired": 0, "read-only": 0, "explicit-only": 0, "cold": 0}
    for r in rows:
        st = r["status"]
        if st in out:
            out[st] += 1
    return out


# ============================================================
# 区块: Owner 路由足迹（Phase 3.3）
# ============================================================
ROUTING_OWNER_ORDER = ["live_app", "live3_app", "live4_go_talk",
                       "live3_svr_api", "live3_svr_admin"]
ROUTING_SESSION_EVENT_CAP = 100  # 单 session 展示事件数上限（>100 时前 50 后 50）


def query_session_routing(conn, days: int, limit: int = 50) -> list:
    """按 session 聚合最近 limit 个 session 的路由摘要，含事件时间线。

    返回 [{
      session_id, first_ts, last_ts, event_count, duration_seconds,
      owners_involved, owner_distribution, events
    }]，按 last_ts DESC 排序。

    实现：两段式查询——先取 session summary，再 IN 一次性取事件。
    """
    cutoff = cutoff_ts(days)

    # Step 1: session summary（按 last_ts 倒序取最近 limit 个）
    summary_rows = conn.execute(
        "SELECT session, MIN(ts), MAX(ts), COUNT(*) "
        "FROM events WHERE ts >= ? AND COALESCE(session,'') != '' "
        "GROUP BY session ORDER BY MAX(ts) DESC LIMIT ?",
        (cutoff, limit),
    ).fetchall()

    if not summary_rows:
        return []

    session_ids = [row[0] for row in summary_rows]
    placeholders = ",".join(["?"] * len(session_ids))

    # Step 2: 批量取事件
    event_rows = conn.execute(
        f"SELECT session, ts, type, name, scope, path "
        f"FROM events WHERE session IN ({placeholders}) AND ts >= ? "
        f"ORDER BY session, ts",
        (*session_ids, cutoff),
    ).fetchall()

    # 按 session 分组事件
    events_by_session = {}
    for sess, ts, etype, name, scope, path in event_rows:
        events_by_session.setdefault(sess, []).append({
            "ts": ts,
            "type": etype,
            "name": name or "",
            "scope": scope or "",
            "path": path or "",
        })

    # 计算 owner 归属（事件级）
    out = []
    for sess_id, first_ts, last_ts, event_count in summary_rows:
        events = events_by_session.get(sess_id, [])
        owner_dist = {}
        for ev in events:
            ow = compute_owner(ev["path"]) if ev["path"] else (
                "live_app" if ev["type"] == "memory_read"
                else "builtin" if ev["type"] == "subagent"
                else "global"
            )
            ev["owner"] = ow
            owner_dist[ow] = owner_dist.get(ow, 0) + 1

        # 事件截断：>100 时前 50 + 后 50
        truncated_count = 0
        kept_events = events
        if len(events) > ROUTING_SESSION_EVENT_CAP:
            truncated_count = len(events) - ROUTING_SESSION_EVENT_CAP
            kept_events = events[:50] + events[-50:]

        # 计算跨度
        try:
            t0 = datetime.strptime(first_ts.rstrip("Z"), "%Y-%m-%dT%H:%M:%S")
            t1 = datetime.strptime(last_ts.rstrip("Z"), "%Y-%m-%dT%H:%M:%S")
            duration_s = int((t1 - t0).total_seconds())
        except Exception:
            duration_s = 0

        owners_involved = [o for o in ROUTING_OWNER_ORDER if o in owner_dist]
        # 把不在 ORDER 里的（builtin/global/unknown 等）追加在尾
        for o in owner_dist:
            if o not in ROUTING_OWNER_ORDER and o not in owners_involved:
                owners_involved.append(o)

        # 抽出 user_prompt 事件单独列出（不夹在普通事件流里）
        prompts = [
            {"ts": ev["ts"], "text": ev["name"]}
            for ev in events
            if ev["type"] == "user_prompt" and ev.get("name")
        ]
        # 普通事件（去掉 user_prompt，避免重复显示）
        non_prompt_events = [ev for ev in kept_events if ev["type"] != "user_prompt"]

        out.append({
            "session_id": sess_id,
            "first_ts": first_ts,
            "last_ts": last_ts,
            "event_count": event_count,
            "duration_seconds": duration_s,
            "owners_involved": owners_involved,
            "owner_distribution": owner_dist,
            "events": non_prompt_events,
            "prompts": prompts,
            "truncated_count": truncated_count,
        })
    return out


def fmt_duration(seconds: int) -> str:
    """秒数 → 友好字符串：xd Xh / Xh Ym / Xm / Xs"""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m" if m else f"{h}h"
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    return f"{d}d {h}h" if h else f"{d}d"
