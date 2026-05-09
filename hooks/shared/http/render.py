#!/usr/bin/env python3
"""Render module: 页面骨架 + 通用 helpers + render() 调度.
按 tab 拆分的 leaf 函数在 overview/usage/context/memory/ai_news/render.py."""
import html
import sqlite3
from urllib.parse import quote

from shared.infra.core import *
from shared.data.queries import *
from shared.data.queries import _collect_known_resources  # `import *` 不带 _

from shared.infra import summary as summary_mod
def _get_summary_status():
    return summary_mod.get_status()


def render_sparkline(daily: list, width: int = 220, height: int = 40, with_axis: bool = True) -> str:
    """生成内联 SVG sparkline + (可选) 时间轴标签. daily = [(day, count)].
    - 全零时显示占位文字
    - 每個點有 <title> hover tooltip 顯示日期+次數
    - with_axis=True 时下方橫軸顯示起止日期 + 峰值提示;
      with_axis=False 时仅 svg, 由调用方自己渲染时间标签"""
    if not daily:
        return ""
    total = sum(c for _, c in daily)
    n = len(daily)
    if total == 0:
        return f"<div class='sparkline-empty'>近 {n} 天均无事件</div>"
    max_val = max(c for _, c in daily) or 1
    max_idx = max(range(n), key=lambda i: daily[i][1])
    pad = 2
    w_avail = width
    h_avail = height - pad * 2
    pts = []
    circles = []
    for i, (day, c) in enumerate(daily):
        x = (i * w_avail / max(n - 1, 1)) if n > 1 else w_avail / 2
        y = pad + (h_avail - (c / max_val) * h_avail)
        pts.append(f"{x:.1f},{y:.1f}")
        is_peak = i == max_idx and c > 0
        r = 2.5 if is_peak else 1.5
        cls = "sparkline-peak" if is_peak else "sparkline-dot"
        circles.append(
            f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{r}' class='{cls}' "
            f"data-tip='{day}: {c} 次'></circle>"
        )
    points_str = " ".join(pts)
    area_pts = f"0,{height} {points_str} {width},{height}"
    svg = (
        f"<svg class='sparkline' viewBox='0 0 {width} {height}' preserveAspectRatio='none'>"
        f"<polygon points='{area_pts}' class='sparkline-area'/>"
        f"<polyline points='{points_str}' fill='none' class='sparkline-line'/>"
        f"{''.join(circles)}"
        f"</svg>"
    )
    if not with_axis:
        return f"<div class='sparkline-wrap'>{svg}</div>"

    # 短日期格式 MM/DD
    def short(day_str):
        return day_str[5:].replace("-", "/") if len(day_str) >= 10 else day_str
    start_label = short(daily[0][0])
    end_label = short(daily[-1][0])
    peak_day = short(daily[max_idx][0])
    peak_val = daily[max_idx][1]

    return (
        f"<div class='sparkline-wrap'>{svg}"
        f"<div class='sparkline-axis'>"
        f"<span>{start_label}</span>"
        f"<span class='sparkline-peak-label' data-tip='峰值日期: {peak_day} · {peak_val} 次'>↑ {peak_val} 次</span>"
        f"<span>{end_label}</span>"
        f"</div>"
        f"</div>"
    )


def _open_url(path: str) -> str:
    from urllib.parse import quote
    return f"/open?path={quote(path, safe='')}"


def _file_link(text: str, path: str) -> str:
    """生成可点击的文件链接. JS 全域委派攔截, 不會跳轉新頁面.
    data-summary=path 讓 JS hover 時懶生成 AI 中文摘要."""
    if not path:
        return html.escape(text)
    url = _open_url(path)
    label = html.escape(text)
    return f"<a href='{url}' class='open-link' data-summary='{html.escape(path)}'>{label}</a>"


def _file_link_plain(text: str, path: str, tip: str = "") -> str:
    """可点击文件链接, 不触发 LLM 摘要. 可选 tip 直接挂在 <a> 上, 仅悬停文字时触发."""
    if not path:
        return html.escape(text)
    url = _open_url(path)
    label = html.escape(text)
    tip_attr = f" data-tip='{html.escape(tip)}'" if tip else ""
    return f"<a href='{url}' class='open-link'{tip_attr}>{label}</a>"


def _render_head(parts: list, owner_filter: str):
    parts.append("<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>")
    parts.append("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    parts.append(f"<title>{LABELS['title']}</title>")
    # Neo-Terminal / Cyberpunk 字体栈: Chakra Petch (display/body angular) + JetBrains Mono (numeric/technical)
    parts.append("<link rel='preconnect' href='https://fonts.googleapis.com'>")
    parts.append("<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>")
    parts.append(
        "<link rel='stylesheet' "
        "href='https://fonts.googleapis.com/css2?"
        "family=Chakra+Petch:wght@400;500;600;700&"
        "family=JetBrains+Mono:wght@400;500;600;700&"
        "display=swap'>"
    )
    # 6 个 feature-first CSS: base 先载入, 之后按 tab 顺序
    parts.append("<link rel='stylesheet' href='/static/shared/base.css'>")
    parts.append("<link rel='stylesheet' href='/static/overview/style.css'>")
    parts.append("<link rel='stylesheet' href='/static/usage/style.css'>")
    parts.append("<link rel='stylesheet' href='/static/context/style.css'>")
    parts.append("<link rel='stylesheet' href='/static/memory/style.css'>")
    parts.append("<link rel='stylesheet' href='/static/ai_news/style.css'>")
    parts.append("</head>")
    parts.append(f"<body data-initial-owner='{html.escape(owner_filter)}'>")
    parts.append("<div class='page'>")


_HEALTH_STATUS_LABEL = {
    "ok": ("✓", "正常"),
    "warn": ("⚠", "注意"),
    "error": ("✗", "异常"),
    "stale": ("·", "未生成"),
}

# lint check 状态图标（独立于 chip 总状态，避免相互污染）
_LINT_CHECK_ICON = {
    "pass": ("✓", "通过"),
    "fail": ("✗", "失败"),
    "warn": ("⚠", "注意"),
    "pending": ("·", "待实现"),
    "skip": ("·", "跳过"),
    "error": ("✗", "异常"),
}


def _fmt_lint_run_time(ts_iso: str) -> str:
    """lint 'last_run' 专用：今 HH:MM / 昨 HH:MM / MM-DD HH:MM
    跟 fmt_relative_time 区别：今天也带"今 "前缀，避免单看 "00:07" 不知道是哪天
    """
    if not ts_iso:
        return ""
    from datetime import datetime, timezone
    try:
        dt = datetime.strptime(ts_iso.rstrip("Z"), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        local = dt.astimezone()
    except Exception:
        return ts_iso
    today = datetime.now().astimezone().date()
    delta = (today - local.date()).days
    if delta == 0:
        return "今 " + local.strftime("%H:%M")
    if delta == 1:
        return "昨 " + local.strftime("%H:%M")
    return local.strftime("%m-%d %H:%M")


def _render_page_header(parts: list, conn=None):
    """穩定骨架的頁面標題層 (永不隨 tab 變動)."""
    status = _get_summary_status()
    parts.append("<header class='page-header'>")
    parts.append("<div class='page-header-inner'>")
    parts.append("<h1 class='page-title'>Claude Code <em>使用统计</em></h1>")
    parts.append("<div class='page-actions'>")
    if conn is not None:
        _render_health_strip(parts, conn)
    parts.append(
        "<div class='summary-meter'>"
        "<span class='summary-meter-label'>AI 摘要</span>"
        f"<span class='summary-meter-quota'>今日 <b id='summary-count'>{status['count']}</b>"
        f"/<span id='summary-limit'>{status['limit']}</span></span>"
        f"<span class='summary-meter-cache'>缓存 <b id='summary-cache-size'>{status['cache_size']}</b></span>"
        "<button class='summary-meter-btn' id='clear-summary-cache-btn'>清理</button>"
        "</div>"
    )
    parts.append("</div>")
    parts.append("</div>")
    parts.append("</header>")


def _render_health_strip(parts: list, conn):
    """工作区健康状态条：[采集 chip] [配置 chip] + 2 个 sheet drawer"""
    health = query_collection_health(conn)
    lint = query_lint_status()
    lint_status = derive_lint_status(lint)
    counts = count_lint_issues(lint)

    # 采集 chip 副标
    coll_status = health["status"]
    coll_count_text = (
        f"{health['events_24h']}/24h"
        if coll_status in ("ok", "warn") and health["events_24h"] > 0
        else f"7d:{health['events_7d']}"
        if health["events_7d"] > 0
        else "—"
    )

    # 配置 chip 副标
    if lint is None:
        lint_count_text = "未生成"
    elif counts["fail"] > 0:
        lint_count_text = f"{counts['fail']} fail"
    elif counts["warn"] > 0:
        lint_count_text = f"{counts['warn']} warn"
    elif counts["pass"] > 0:
        lint_count_text = f"{counts['pass']} pass"
    else:
        lint_count_text = "—"

    parts.append("<div class='health-strip' aria-label='工作区健康状态'>")
    parts.append(_render_health_chip("collection-health-sheet", "采集", coll_status, coll_count_text))
    parts.append(_render_health_chip("lint-health-sheet", "配置", lint_status, lint_count_text))
    parts.append("</div>")

    _render_collection_health_sheet(parts, health)
    _render_lint_health_sheet(parts, lint, counts)


def _render_health_chip(sheet_id: str, label: str, status: str, count_text: str) -> str:
    icon, _ = _HEALTH_STATUS_LABEL.get(status, ("?", ""))
    return (
        f"<button class='health-chip health-chip-{html.escape(status)} sheet-btn' "
        f"data-sheet-target='{html.escape(sheet_id)}'>"
        f"<span class='health-chip-label'>{html.escape(label)}</span>"
        f"<span class='health-chip-icon'>{html.escape(icon)}</span>"
        f"<span class='health-chip-count'>{html.escape(count_text)}</span>"
        f"</button>"
    )


def _render_collection_health_sheet(parts: list, health: dict):
    parts.append("<div class='sheet' id='collection-health-sheet'>")
    parts.append("<div class='sheet-head'><h3>采集健康</h3></div>")
    parts.append("<div class='sheet-body'>")

    # 总览
    icon, label = _HEALTH_STATUS_LABEL.get(health["status"], ("?", ""))
    parts.append("<div class='health-summary'>")
    parts.append(f"<span class='health-summary-status status-{html.escape(health['status'])}'>{html.escape(icon)} {html.escape(label)}</span>")
    parts.append(f"<span class='health-summary-meta'>历史 {health['total_events']} 事件 · 24h {health['events_24h']} · 7d {health['events_7d']}</span>")
    if health["last_event_at"]:
        parts.append(f"<span class='health-summary-meta'>最近事件: {html.escape(fmt_relative_time(health['last_event_at']))}</span>")
    if health["empty_session_count_24h"] > 0:
        parts.append(f"<span class='health-summary-meta status-warn'>24h 空 session {health['empty_session_count_24h']} 条 ({health['empty_session_pct_24h']:.1f}%)</span>")
    parts.append("</div>")

    # 各 type
    parts.append("<h4 class='sheet-subtitle'>各事件类型最近时间</h4>")
    parts.append("<table class='health-type-table'>")
    parts.append("<thead><tr><th>type</th><th>label</th><th>最近</th></tr></thead><tbody>")
    for t in health["per_type_last_seen"]:
        last = fmt_relative_time(t["last_seen"]) if t["last_seen"] else "(从未)"
        cls = "" if t["last_seen"] else " class='last-never'"
        parts.append(
            f"<tr{cls}><td><code>{html.escape(t['type'])}</code></td>"
            f"<td>{html.escape(t['label'])}</td>"
            f"<td>{html.escape(last)}</td></tr>"
        )
    parts.append("</tbody></table>")

    # 错误日志
    err = health["errors"]
    parts.append("<h4 class='sheet-subtitle'>tracker-errors.log</h4>")
    if not err["exists"]:
        parts.append("<p class='health-empty'>未发现错误日志文件（采集层无错误记录）</p>")
    else:
        parts.append(
            f"<p class='health-meta'>总行数: {err['total_lines']} · 24h: {err['recent_24h']} · 7d: {err['recent_7d']}</p>"
        )
        if err["last_20_lines"]:
            parts.append("<pre class='health-log-preview'>")
            for line in err["last_20_lines"]:
                parts.append(html.escape(line) + "\n")
            parts.append("</pre>")
        else:
            parts.append("<p class='health-empty'>日志为空</p>")

    parts.append("</div></div>")  # /sheet-body /sheet


def _render_lint_health_sheet(parts: list, lint: dict | None, counts: dict):
    parts.append("<div class='sheet' id='lint-health-sheet'>")
    parts.append("<div class='sheet-head'><h3>配置健康（workspace-lint）</h3></div>")
    parts.append("<div class='sheet-body'>")
    parts.append(
        "<p class='section-intro'>"
        "8 项配置自动检查。有 ⚠ 或 ✗ 时直接看下面哪条挂了。"
        "</p>"
    )

    if lint is None:
        parts.append(
            "<p class='health-empty'>"
            "<code>~/Desktop/ai-project/data/lint-status.json</code> 尚未生成<br>"
            "请确保 lint hook 已注册，或手动运行 "
            "<code>python3 ~/Desktop/ai-project/hooks/workspace-lint/lint_runner.py</code>"
            "</p>"
        )
        parts.append("</div></div>")  # /sheet-body /sheet
        return

    # 元数据
    last_run = lint.get("last_run") or "?"
    trigger = lint.get("trigger") or "?"
    duration = lint.get("duration_ms")
    fp = lint.get("fingerprint") or ""
    fp_short = fp[:12] if fp else "—"
    parts.append("<div class='health-summary'>")
    parts.append(f"<span class='health-summary-meta'>上次跑: {html.escape(_fmt_lint_run_time(last_run))}</span>")
    parts.append(f"<span class='health-summary-meta'>触发: <code>{html.escape(trigger)}</code></span>")
    if duration is not None:
        parts.append(f"<span class='health-summary-meta'>耗时: {html.escape(str(duration))} ms</span>")
    parts.append(f"<span class='health-summary-meta'>fingerprint: <code>{html.escape(fp_short)}…</code></span>")
    parts.append("</div>")

    # 计数行
    parts.append("<div class='health-summary'>")
    parts.append(f"<span class='health-summary-meta status-ok'>{counts['pass']} pass</span>")
    if counts["warn"]:
        parts.append(f"<span class='health-summary-meta status-warn'>{counts['warn']} warn</span>")
    if counts["fail"]:
        parts.append(f"<span class='health-summary-meta status-error'>{counts['fail']} fail</span>")
    if counts["pending"]:
        parts.append(f"<span class='health-summary-meta'>{counts['pending']} pending</span>")
    parts.append("</div>")

    # 错误总览
    err = lint.get("error")
    if err:
        parts.append(
            f"<p class='status-error'>Runner 错误: {html.escape(str(err.get('message','')))} "
            f"(exit_code={html.escape(str(err.get('exit_code','?')))})</p>"
        )

    # 8 条 lint 列表
    parts.append("<h4 class='sheet-subtitle'>检查项</h4>")
    parts.append("<ul class='lint-check-list'>")
    for c in lint.get("checks") or []:
        cid = c.get("id", "")
        name = c.get("name", cid)
        st = c.get("status", "?")
        issues = c.get("issues") or []
        icon, _ = _LINT_CHECK_ICON.get(st, ("·", ""))
        parts.append(f"<li class='lint-check status-{html.escape(st)}'>")
        parts.append(
            f"<span class='lint-check-head'>"
            f"<span class='lint-check-icon'>{html.escape(icon)}</span>"
            f"<span class='lint-check-name'>{html.escape(name)}</span>"
            f"<span class='lint-check-id'>{html.escape(cid)}</span>"
            f"<span class='lint-check-status'>{html.escape(st)} · {len(issues)} issue{'s' if len(issues) != 1 else ''}</span>"
            f"</span>"
        )
        if issues and st in ("fail", "warn", "error"):
            parts.append("<ul class='lint-issue-list'>")
            for issue in issues[:20]:  # 最多 20 条避免炸
                msg = issue.get("message", "") or ""
                file_ = issue.get("file") or ""
                line = issue.get("line")
                ref = issue.get("ref") or issue.get("target") or issue.get("skill_ref") or ""
                pos = ""
                if file_:
                    pos = file_
                    if line is not None:
                        pos += f":{line}"
                parts.append("<li class='lint-issue'>")
                if pos:
                    parts.append(f"<code>{html.escape(pos)}</code> ")
                parts.append(html.escape(msg))
                if ref:
                    parts.append(f" <code class='lint-issue-ref'>{html.escape(str(ref))}</code>")
                parts.append("</li>")
            if len(issues) > 20:
                parts.append(f"<li class='lint-issue-more'>… 还有 {len(issues) - 20} 条</li>")
            parts.append("</ul>")
        elif st == "pending":
            # pending 单独提示一下不当作问题
            parts.append("<p class='lint-check-pending-note'>未实现（Phase 2.5）</p>")
        parts.append("</li>")
    parts.append("</ul>")

    parts.append("</div></div>")


def _render_time_pills(parts: list, days: int, owner_filter: str,
                        usage_days: int = None, routing_days: int = None,
                        anchor: str = "overview"):
    """總覽 pills（控制 ?days=N，但保留 usage_days / routing_days 不联动）.
    用 ?tab= 让服务端预渲染 active tab，避免客户端切换闪烁."""
    parts.append("<div class='pills time-pills'>")
    for d in [1, 7, 30, 90, 365]:
        label = "1天" if d == 1 else "7天" if d == 7 else "30天" if d == 30 else "90天" if d == 90 else "1年"
        url_parts = [f"days={d}"]
        if usage_days is not None:
            url_parts.append(f"usage_days={usage_days}")
        if routing_days is not None:
            url_parts.append(f"routing_days={routing_days}")
        if owner_filter:
            url_parts.append(f"owner={owner_filter}")
        url_parts.append(f"tab={anchor}")
        url = "/?" + "&".join(url_parts)
        cls = "pill active" if d == days else "pill"
        parts.append(f"<a class='{cls}' href='{url}'>{label}</a>")
    parts.append("</div>")


OWNER_PREFERRED = [
    "global", "builtin", "plugin", "live_app",
    "live3_app", "live4_go_talk", "live3_svr_api",
    "live3_svr_admin", "live3_svr_im", "live3_svr_pay",
]

# Tab 定义: (id, label)
TABS = [
    ("overview",  "总览"),
    ("usage",     "工具使用"),
    ("context",   "路由"),  # Phase 3.3：原"上下文"改为"路由"，tab id 保留
    ("memory",    "记忆"),
    ("news",      "每日AI大事"),
]


def _render_tab_bar(parts: list, active_tab: str = "overview"):
    parts.append("<div class='tab-bar'>")
    for tab_id, label in TABS:
        cls = "tab active" if tab_id == active_tab else "tab"
        parts.append(f"<a class='{cls}' href='#{tab_id}' data-tab='{tab_id}'>{label}</a>")
    parts.append("</div>")


_SUMMARY_CACHE = {}


def _render_footer(parts: list):
    parts.append(f"<footer>数据源: SQLite · jsonl 仅作备份 · {LABELS['refresh_hint']}</footer>")
    parts.append("</div>")  # page end
    # 5 个 feature-first JS (memory 无独立交互, 不出 script). base 先加载建立 window.__dashboard,
    # 其余 feature 读取 window.__dashboard.showToast / flipOpenOrder
    parts.append("<script defer src='/static/shared/base.js'></script>")
    parts.append("<script defer src='/static/overview/app.js'></script>")
    parts.append("<script defer src='/static/usage/app.js'></script>")
    parts.append("<script defer src='/static/context/app.js'></script>")
    parts.append("<script defer src='/static/ai_news/app.js'></script>")
    parts.append("</body></html>")


# ============================================================
# 区块: 主渲染函数 (数据加载 + 子函数调度)
# ============================================================
def render(days: int, owner_filter: str = "",
           usage_days: int = None, routing_days: int = None,
           active_tab: str = "overview") -> str:
    """
    `days` = 总览（overview）时间窗
    `usage_days` = 工具使用 tab 时间窗（未传则与 days 同步）
    `routing_days` = 路由 tab 时间窗（未传则与 days 同步）
    """
    if usage_days is None:
        usage_days = days
    if routing_days is None:
        routing_days = days
    conn = sqlite3.connect(DB_FILE)

    # ===== 加载 Active / Cold 数据 (工具使用 tab 用 usage_days) =====
    active_data = {
        etype: attach_owner_active(etype, query_counts(conn, etype, usage_days))
        for etype, _ in CATEGORIES
    }
    cold_data_by_id = {}
    overridden_user = set()
    for section_def in COLD_SECTIONS:
        cold_items, universe, overridden = compute_cold_items(section_def, active_data)
        cold_data_by_id[section_def["id"]] = {
            "def": section_def,
            "cold": cold_items,
            "universe": universe,
            "universe_count": len(universe),
        }
        if overridden:
            overridden_user |= overridden

    # ===== 加载摘要/衍生指标 (总览 hero 用 days) =====
    total = conn.execute("SELECT COUNT(*) FROM events WHERE ts >= ?", (cutoff_ts(days),)).fetchone()[0]
    sessions = conn.execute(
        "SELECT COUNT(DISTINCT session) FROM events WHERE ts >= ? AND session != ''",
        (cutoff_ts(days),),
    ).fetchone()[0]

    # 工具使用 tab 的 sessions / paired 配对率走 usage_days
    sessions_maps = {etype: query_sessions_count(conn, etype, usage_days) for etype, _ in CATEGORIES}
    paired_maps = {etype: query_paired_count(conn, etype, usage_days) for etype, _ in CATEGORIES}
    last_seen_maps = {sd["event_type"]: query_last_seen(conn, sd["event_type"]) for sd in COLD_SECTIONS}

    # ===== 加载面板数据 =====
    daily_counts = query_daily_counts(conn, days)
    # hero metric strip 用无 axis 版本; axis 信息由 hero 自己渲染
    sparkline_svg = render_sparkline(daily_counts, with_axis=False)
    # 提取 sparkline 起止 + 峰值 (供 hero 文本块用)
    if daily_counts and any(c for _, c in daily_counts):
        max_idx = max(range(len(daily_counts)), key=lambda i: daily_counts[i][1])
        peak_day_full = daily_counts[max_idx][0]
        peak_val = daily_counts[max_idx][1]
        spark_meta = {
            "start": daily_counts[0][0][5:].replace("-", "/"),
            "end": daily_counts[-1][0][5:].replace("-", "/"),
            "peak_day": peak_day_full[5:].replace("-", "/"),
            "peak_val": peak_val,
        }
    else:
        spark_meta = None
    owner_activity = query_owner_activity(conn, days)
    # Today · Console Stack 新数据
    owner_dailies = query_owner_dailies(conn, days)
    owner_sessions = query_owner_session_counts(conn, days)
    recent_stream = query_recent_events(conn, days, limit=30)
    # _collect_owners 已迁到 usage.render, 这里 late import 避免循环依赖
    from usage.render import _collect_owners
    ordered_owners = _collect_owners(active_data, cold_data_by_id)

    # Phase 3.3：Owner 路由足迹（context tab 重做）
    session_routes = query_session_routing(conn, routing_days, limit=50)

    mem_files = list_memory_browser()
    compact_files = list_compact_notes()

    # ===== 渲染 HTML (穩定骨架 + 自包含 tab) =====
    parts = []
    _render_head(parts, owner_filter)

    # 穩定骨架: 永不變動的 header + sticky tab bar
    _render_page_header(parts, conn=conn)
    _render_tab_bar(parts, active_tab)
    _ac = lambda t: " active" if t == active_tab else ""

    # Tab viewport: 固定 min-height, 內部各 tab 自帶所需控件
    parts.append("<div class='tab-viewport'>")

    # 各 tab 通过各自模块的 render_X 入口调度 (feature-first 结构)
    from overview.render import render_overview
    from usage.render import render_usage
    from context.render import render_context
    from memory.render import render_memory
    from ai_news.render import render_news

    # Tab 1: 总览
    hero_agg = query_hero_aggregates(conn, days)
    parts.append(f"<div class='tab-content{_ac('overview')}' data-tab='overview'>")
    render_overview(parts, days=days, owner_filter=owner_filter,
                    total=total, sessions=sessions,
                    sparkline_svg=sparkline_svg, spark_meta=spark_meta,
                    hero_agg=hero_agg,
                    owner_activity=owner_activity,
                    owner_dailies=owner_dailies,
                    owner_sessions=owner_sessions,
                    recent_stream=recent_stream,
                    conn=conn,
                    usage_days=usage_days, routing_days=routing_days)
    parts.append("</div>")

    # Tab 2: 工具使用
    parts.append(f"<div class='tab-content{_ac('usage')}' data-tab='usage'>")
    render_usage(parts, days=usage_days, owner_filter=owner_filter,
                 overview_days=days, routing_days=routing_days,
                 ordered_owners=ordered_owners,
                 active_data=active_data, cold_data_by_id=cold_data_by_id,
                 sessions_maps=sessions_maps, paired_maps=paired_maps,
                 last_seen_maps=last_seen_maps, overridden_user=overridden_user,
                 conn=conn)
    parts.append("</div>")

    # Tab 3: 上下文
    parts.append(f"<div class='tab-content{_ac('context')}' data-tab='context'>")
    render_context(parts, session_routes=session_routes, days=routing_days,
                   overview_days=days, usage_days=usage_days,
                   owner_filter=owner_filter)
    parts.append("</div>")

    # Tab 4: 记忆
    parts.append(f"<div class='tab-content{_ac('memory')}' data-tab='memory'>")
    render_memory(parts, mem_files=mem_files, compact_files=compact_files)
    parts.append("</div>")

    # Tab 5: 每日 AI 大事
    parts.append(f"<div class='tab-content{_ac('news')}' data-tab='news'>")
    render_news(parts)
    parts.append("</div>")

    parts.append("</div>")  # tab-viewport end
    _render_footer(parts)

    conn.close()
    return "".join(parts)


def _open_flip_card(parts: list, card_classes: str):
    """開一張翻面卡 (front 段)."""
    parts.append(f"<div class='{card_classes} flip-card'>")
    parts.append("<div class='flip-inner'>")
    parts.append("<div class='flip-front'>")


def _between_flip_faces(parts: list):
    parts.append("</div><div class='flip-back'>")


def _close_flip_card(parts: list):
    parts.append("</div></div>")  # close flip-back, flip-inner
    parts.append("</div>")  # close flip-card


# ============================================================
# 区块: 背面渲染通用 helpers (抽離重複 markup)
# ============================================================
def _flip_stat(label: str, value, cls: str = "", small: str = "") -> str:
    """單個 stat 單元. cls: 'accent'/'warning'/'danger'/''. small: hover tooltip 字串."""
    value_cls = f"flip-stat-value {cls}".strip()
    small_html = f" <small data-tip='{html.escape(small)}'>?</small>" if small else ""
    return (
        f"<div class='flip-stat'>"
        f"<span class='flip-stat-label'>{label}</span>"
        f"<span class='{value_cls}'>{value}{small_html}</span>"
        f"</div>"
    )


def _flip_stat_grid(cells: list) -> str:
    """將多個 _flip_stat 字串包進 grid 容器."""
    return f"<div class='flip-stat-grid'>{''.join(cells)}</div>"


def _flip_back_section(label: str, inner: str) -> str:
    """背面子區塊 (帶小標)."""
    return (
        f"<div class='flip-back-section'>"
        f"<div class='flip-stat-label'>{label}</div>"
        f"{inner}"
        f"</div>"
    )


def _flip_back_title(title: str) -> str:
    return f"<div class='flip-back-title'>{title}</div>"


def _owner_bar_row(label_html: str, count: int, max_total: int) -> str:
    """單行 owner/type 分布條."""
    pct = (count / max(max_total, 1)) * 100
    return (
        f"<div class='owner-bar-row'>"
        f"{label_html}"
        f"<div class='owner-bar'><div class='owner-bar-fill' style='width:{pct:.0f}%'></div></div>"
        f"<span class='owner-bar-num'>{count}</span>"
        f"</div>"
    )


def _owner_col(label_html: str, count: int, max_count: int) -> str:
    """單列垂直柱."""
    pct = (count / max(max_count, 1)) * 100
    return (
        f"<div class='owner-col'>"
        f"<span class='owner-col-value'>{count}</span>"
        f"<div class='owner-col-bar'><div class='owner-col-fill' style='height:{pct:.0f}%'></div></div>"
        f"<span class='owner-col-label'>{label_html}</span>"
        f"</div>"
    )


def _owner_dist_html(items: list, label_fn, limit: int = 6, columns: bool = False) -> str:
    """把 dict/list 渲染為分布. items 可以是 dict 或 [(key, count)].
    columns=True 用垂直柱狀圖, 否則用水平長條.
    label_fn 接收 key 返回 label HTML (如 owner-tag 或 span)."""
    if isinstance(items, dict):
        pairs = sorted(items.items(), key=lambda x: -x[1])
    else:
        pairs = items
    if not pairs:
        return ""
    if columns:
        max_count = max(c for _, c in pairs) or 1
        cols = [_owner_col(label_fn(k), c, max_count) for k, c in pairs[:limit]]
        return f"<div class='owner-col-chart'>{''.join(cols)}</div>"
    total = sum(c for _, c in pairs) or 1
    rows = [_owner_bar_row(label_fn(k), c, total) for k, c in pairs[:limit]]
    return f"<div class='owner-dist'>{''.join(rows)}</div>"


def _owner_tag_label(owner: str) -> str:
    cls = html.escape(owner)
    label = html.escape(owner_display(owner))
    return f"<span class='owner-tag {cls}'>{label}</span>"


# _HERO_BACK_DISPATCH 迁到 overview/render.py (hero 相关函数都在那)


