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


def render_sparkline(daily: list, width: int = 220, height: int = 40) -> str:
    """生成内联 SVG sparkline + 时间轴标签. daily = [(day, count)].
    - 全零时显示占位文字
    - 每個點有 <title> hover tooltip 顯示日期+次數
    - 下方橫軸顯示起止日期 + 峰值提示"""
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

    # 短日期格式 MM/DD
    def short(day_str):
        return day_str[5:].replace("-", "/") if len(day_str) >= 10 else day_str
    start_label = short(daily[0][0])
    end_label = short(daily[-1][0])
    peak_day = short(daily[max_idx][0])
    peak_val = daily[max_idx][1]

    return (
        f"<div class='sparkline-wrap'>"
        f"<svg class='sparkline' viewBox='0 0 {width} {height}' preserveAspectRatio='none'>"
        f"<polygon points='{area_pts}' class='sparkline-area'/>"
        f"<polyline points='{points_str}' fill='none' class='sparkline-line'/>"
        f"{''.join(circles)}"
        f"</svg>"
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


def _render_page_header(parts: list):
    """穩定骨架的頁面標題層 (永不隨 tab 變動)."""
    status = _get_summary_status()
    parts.append("<header class='page-header'>")
    parts.append("<div class='page-header-inner'>")
    parts.append("<h1 class='page-title'>Claude Code <em>使用统计</em></h1>")
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
    parts.append("</header>")


def _render_time_pills(parts: list, days: int, owner_filter: str):
    """獨立的時間窗口切換 pills (usage tab 等需要但不含完整 hero 的 tab 使用)."""
    parts.append("<div class='pills time-pills'>")
    for d in [1, 7, 30, 90, 365]:
        label = "1天" if d == 1 else "7天" if d == 7 else "30天" if d == 30 else "90天" if d == 90 else "1年"
        url_parts = [f"days={d}"]
        if owner_filter:
            url_parts.append(f"owner={owner_filter}")
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
    ("context",   "上下文"),
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
def render(days: int, owner_filter: str = "") -> str:
    conn = sqlite3.connect(DB_FILE)

    # ===== 加载 Active / Cold 数据 =====
    active_data = {
        etype: attach_owner_active(etype, query_counts(conn, etype, days))
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

    # ===== 加载摘要/衍生指标 =====
    total = conn.execute("SELECT COUNT(*) FROM events WHERE ts >= ?", (cutoff_ts(days),)).fetchone()[0]
    sessions = conn.execute(
        "SELECT COUNT(DISTINCT session) FROM events WHERE ts >= ? AND session != ''",
        (cutoff_ts(days),),
    ).fetchone()[0]
    total_all = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    cold_total = sum(len(d["cold"]) for d in cold_data_by_id.values())
    this_week, last_week = query_week_over_week(conn)

    sessions_maps = {etype: query_sessions_count(conn, etype, days) for etype, _ in CATEGORIES}
    paired_maps = {etype: query_paired_count(conn, etype, days) for etype, _ in CATEGORIES}
    last_seen_maps = {sd["event_type"]: query_last_seen(conn, sd["event_type"]) for sd in COLD_SECTIONS}

    # ===== 加载面板数据 =====
    daily_counts = query_daily_counts(conn, days)
    sparkline_svg = render_sparkline(daily_counts)
    owner_activity = query_owner_activity(conn, days)
    health = query_subproject_health(conn, days)
    # _collect_owners 已迁到 usage.render, 这里 late import 避免循环依赖
    from usage.render import _collect_owners
    ordered_owners = _collect_owners(active_data, cold_data_by_id)

    # CLAUDE.md 分析
    weighted_hits = build_weighted_event_counts(conn)
    known_names = _collect_known_resources(conn)
    claude_analyses = []
    for md in list_claude_mds():
        analysis = analyze_claude_md(md["path"], known_names, weighted_hits)
        if analysis:
            analysis["display_name"] = md["name"]
            analysis["scope"] = md["scope"]
            claude_analyses.append(analysis)

    mem_files = list_memory_browser()
    compact_files = list_compact_notes()

    # ===== 渲染 HTML (穩定骨架 + 自包含 tab) =====
    parts = []
    _render_head(parts, owner_filter)

    # 穩定骨架: 永不變動的 header + sticky tab bar
    _render_page_header(parts)
    _render_tab_bar(parts, "overview")

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
    parts.append("<div class='tab-content active' data-tab='overview'>")
    render_overview(parts, days=days, owner_filter=owner_filter,
                    total=total, sessions=sessions, total_all=total_all, cold_total=cold_total,
                    this_week=this_week, last_week=last_week,
                    sparkline_svg=sparkline_svg, hero_agg=hero_agg,
                    owner_activity=owner_activity, health=health, conn=conn)
    parts.append("</div>")

    # Tab 2: 工具使用
    parts.append("<div class='tab-content' data-tab='usage'>")
    render_usage(parts, days=days, owner_filter=owner_filter,
                 ordered_owners=ordered_owners,
                 active_data=active_data, cold_data_by_id=cold_data_by_id,
                 sessions_maps=sessions_maps, paired_maps=paired_maps,
                 last_seen_maps=last_seen_maps, overridden_user=overridden_user,
                 conn=conn)
    parts.append("</div>")

    # Tab 3: 上下文
    parts.append("<div class='tab-content' data-tab='context'>")
    render_context(parts, claude_analyses=claude_analyses)
    parts.append("</div>")

    # Tab 4: 记忆
    parts.append("<div class='tab-content' data-tab='memory'>")
    render_memory(parts, mem_files=mem_files, compact_files=compact_files)
    parts.append("</div>")

    # Tab 5: 每日 AI 大事
    parts.append("<div class='tab-content' data-tab='news'>")
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
    esc = html.escape(owner)
    return f"<span class='owner-tag {esc}'>{esc}</span>"


# _HERO_BACK_DISPATCH 迁到 overview/render.py (hero 相关函数都在那)


