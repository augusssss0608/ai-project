#!/usr/bin/env python3
"""Render module: HTML 渲染 helpers + 所有 _render_* 函數 + render() orchestrator.
依賴 core + queries."""
import os
import re
import html
import sqlite3
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from usage_web_core import *
from usage_web_core import (
    _init_tiktoken, _TIKTOKEN_STATUS, _TOKEN_CACHE,
)
from usage_web_queries import *
# `import *` 排除底線開頭, 顯式 import render 需要的 queries 私有名
from usage_web_queries import _collect_known_resources

# Summary module: render 需要讀取 summary status 在 page-header meter 顯示
import usage_web_summary as summary_mod
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


def _owner_link(owner: str, days: int) -> str:
    """生成切换 owner 的 URL."""
    parts = [f"days={days}"]
    if owner:
        parts.append(f"owner={owner}")
    return "/?" + "&".join(parts)


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


def _file_preview(path: str, limit: int = 500) -> str:
    """读取文件原文前 N 字符作为 tooltip 预览, 跳过 YAML frontmatter."""
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(4096)
    except Exception:
        return ""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            text = text[end + 4:]
    text = text.lstrip()
    if len(text) > limit:
        text = text[:limit] + "…"
    return text


def cold_row_with_owner(
    name_text: str, path: str, owner: str, last_seen_str: str = "",
    archive_type: str = "", archive_scope: str = "", disabled: bool = False,
) -> str:
    name_html = _file_link(name_text, path)
    owner_tip = f" data-tip='{html.escape(path)}'" if path else ""
    owner_html = f"<span class='owner-tag {html.escape(owner)}'{owner_tip}>{html.escape(owner)}</span>"
    seen_html = f"<span class='last-seen'>{last_seen_str}</span>" if last_seen_str else ""
    archive_html = ""
    if archive_type and archive_scope:
        btn_label = "启用" if disabled else "禁用"
        btn_action = "restore" if disabled else "archive"
        btn_cls = "archive-btn restored" if disabled else "archive-btn"
        archive_html = (
            f"<button class='{btn_cls}' "
            f"data-action='{btn_action}' "
            f"data-type='{html.escape(archive_type)}' "
            f"data-name='{html.escape(name_text)}' "
            f"data-scope='{html.escape(archive_scope)}'>"
            f"{btn_label}</button>"
        )
    disabled_cls = " disabled-item" if disabled else ""
    return (
        f"<li data-owner='{html.escape(owner)}' class='{disabled_cls.strip()}'>"
        f"<span class='name'>{name_html}</span>"
        f"{owner_html}"
        f"{seen_html}"
        f"{archive_html}"
        f"</li>"
    )


def render_risk(parts: list, label_key: str, items: list, total_count: int, name_fmt, universe=None):
    count = len(items)
    cls = severity_cls(count, total_count)
    pct = (count / max(total_count, 1)) * 100 if total_count else 0
    _open_flip_card(parts, f"risk {cls}")
    parts.append(
        f"<div class='risk-head'><span class='risk-title'>{LABELS[label_key]}</span>"
        f"<span class='risk-count'>{count} / {total_count}</span></div>"
    )
    parts.append(f"<div class='risk-bar'><div class='risk-bar-fill' style='width:{pct:.0f}%'></div></div>")
    parts.append("<ul class='risk-list'>")
    if count == 0:
        parts.append(f"<li style='justify-content:center;color:var(--text-faint)'>{LABELS['all_hot']}</li>")
    else:
        for item in items:
            parts.append(name_fmt(item))
    parts.append("</ul>")
    _between_flip_faces(parts)
    progress = query_cold_progress(None, universe or [], items)
    _render_cold_back(parts, label_key, progress)
    _close_flip_card(parts)


# ============================================================
# 区块: 主渲染函数
# ============================================================
# ============================================================
# 区块: render 子函数 (按页面区块拆分)
# ============================================================
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
    parts.append("<link rel='stylesheet' href='/style.css'>")
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


def _render_hero(parts: list, days: int, owner_filter: str,
                 total: int, sessions: int, total_all: int, cold_total: int,
                 this_week: int, last_week: int, sparkline_svg: str,
                 hero_agg: dict = None):
    """Overview tab 的完整 hero body: 副文案 + 時間 pills + 4 卡 summary + sparkline.
    頁面 H1 已由 _render_page_header 渲染，此函數不再輸出標題。"""
    wow_pct = fmt_pct_change(this_week, last_week)
    wow_cls = "success" if this_week > last_week else ("warning" if this_week < last_week else "")

    parts.append("<div class='hero'>")
    parts.append("<div class='hero-top'><div class='hero-copy'>")
    cold_danger = f"<span class='danger'>{cold_total} 项</span>" if cold_total else "<b>0 项</b>"
    wow_html = f"<span class='wow {wow_cls}'>近 7 天 {this_week} 次 (较前 7 天 {wow_pct})</span>"
    parts.append(
        f"<div class='hero-sub'>过去 {days} 天共触发 <b>{total}</b> 次，"
        f"分布在 <b>{sessions}</b> 个会话，装饰品候选 {cold_danger}</div>"
        f"<div class='hero-sub hero-wow'>{wow_html}</div>"
    )
    parts.append("</div>")
    _render_time_pills(parts, days, owner_filter)
    parts.append("</div>")  # hero-top

    # 4 张摘要卡片 (每張可翻面)
    parts.append("<div class='summary'>")
    sessions_pct = min(100, sessions * 2) if sessions else 0
    metric_specs = [
        ("window", LABELS['time_window'], f"{days} 天", '<div class="bar"><div class="bar-fill" style="width:100%"></div></div>', None),
        ("events", LABELS['events_in_window'], None, sparkline_svg, total),
        ("sessions", LABELS['sessions_in_window'], None, f'<div class="bar"><div class="bar-fill" style="width:{sessions_pct:.0f}%"></div></div>', sessions),
        ("all_time", LABELS['total_events'], None, '<div class="bar"><div class="bar-fill" style="width:100%"></div></div>', total_all),
    ]
    for slot, label, static_val, extra, countup_val in metric_specs:
        _open_flip_card(parts, "metric")
        parts.append(f"<div class='metric-label'>{label}</div>")
        if static_val:
            parts.append(f"<div class='metric-value'>{static_val}</div>")
        else:
            parts.append(f"<div class='metric-value' data-countup='{countup_val}'>0</div>")
        parts.append(extra)
        _between_flip_faces(parts)
        if hero_agg:
            _render_hero_metric_back(parts, slot, hero_agg, days)
        _close_flip_card(parts)
    parts.append("</div>")
    parts.append("</div>")  # hero end


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


def _collect_owners(active_data: dict, cold_data_by_id: dict) -> list:
    """从 active + cold 数据收集所有出现的 owner, 按 preferred 排序."""
    all_owners = set()
    for rows in active_data.values():
        for r in rows:
            if r[4]:
                all_owners.add(r[4])
    for data in cold_data_by_id.values():
        for item in data["cold"]:
            if item.get("owner"):
                all_owners.add(item["owner"])
    ordered = []
    for o in OWNER_PREFERRED:
        if o in all_owners:
            ordered.append(o)
            all_owners.discard(o)
    ordered.extend(sorted(all_owners))
    return ordered


def _render_owner_filter(parts: list, ordered_owners: list, owner_filter: str):
    parts.append("<div class='owner-filter' id='owner-filter'>")
    parts.append("<span class='owner-filter-label'>按目录归属筛选:</span>")
    all_cls = "owner-chip" + ("" if owner_filter else " active")
    parts.append(f"<a class='{all_cls}' href='#' data-owner=''>全部</a>")
    for o in ordered_owners:
        cls = "owner-chip" + (" active" if owner_filter == o else "")
        parts.append(f"<a class='{cls}' href='#' data-owner='{html.escape(o)}'>{html.escape(o)}</a>")
    parts.append("</div>")


def _render_today_panel(parts: list, owner_activity: dict, days: int = 7, conn=None):
    parts.append("<div class='section'>")
    parts.append(f"<div class='section-head'><h2>{LABELS['today_panel']}</h2>"
                 "<span class='meta'>各目录归属的最近活动</span></div>")
    parts.append("<div class='today-grid'>")
    sorted_owners = sorted(
        owner_activity.items(),
        key=lambda x: x[1]["last_ts"], reverse=True,
    )
    if not sorted_owners:
        parts.append(f"<div class='empty-note'>{EMPTY_STATES['no_events']}</div>")
    for owner, info in sorted_owners:
        ts = info["last_ts"]
        d_ago = days_ago(ts) if ts else -1
        if d_ago == 0 and ts:
            ago_str = fmt_local_time(ts) or "今天"
        elif d_ago > 0:
            ago_str = f"{d_ago} 天前"
        else:
            ago_str = "—"
        owner_esc = html.escape(owner)
        _open_flip_card(parts, f"today-card")
        parts.append(f"<div class='today-head'><span class='owner-tag {owner_esc}'>{owner_esc}</span>"
                     f"<span class='today-meta'>{info['event_count']} 次 · {ago_str}</span></div>")
        parts.append("<ul class='today-list'>")
        for item in info["recent_items"][:5]:
            name, etype = item[0], item[1]
            ts2 = item[2] if len(item) > 2 else ""
            time_str = fmt_relative_time(ts2) if ts2 else ""
            type_label = next((l for t, l, _ in EVENT_TYPES if t == etype), etype)
            parts.append(
                f"<li><span class='today-type'>{html.escape(type_label)}</span>"
                f"<span class='today-name'>{html.escape(name)}</span>"
                f"<span class='today-time'>{time_str}</span></li>"
            )
        if not info["recent_items"]:
            parts.append(f"<li class='empty-note'>{EMPTY_STATES['no_data']}</li>")
        parts.append("</ul>")
        _between_flip_faces(parts)
        if conn:
            back = query_owner_back(conn, owner, days)
            _render_today_back(parts, owner, back, days)
        _close_flip_card(parts)
    parts.append("</div></div>")


def _render_health_panel(parts: list, health: dict, days: int = 7, conn=None):
    parts.append("<div class='section'>")
    parts.append(f"<div class='section-head'><h2>{LABELS['health_panel']}</h2>"
                 "<span class='meta'>live_app monorepo 子项目活动状态</span></div>")
    parts.append("<div class='health-grid'>")
    for owner, info in health.items():
        ts = info["last_ts"]
        d_ago = days_ago(ts) if ts else -1
        if d_ago < 0:
            health_cls = "dim"; ago_str = "从未活动"
        elif d_ago == 0:
            health_cls = "hot"; ago_str = "今天"
        elif d_ago <= 3:
            health_cls = "warm"; ago_str = f"{d_ago} 天前"
        elif d_ago <= 7:
            health_cls = "cool"; ago_str = f"{d_ago} 天前"
        else:
            health_cls = "cold"; ago_str = f"{d_ago} 天前"
        _open_flip_card(parts, f"health-card {health_cls}")
        parts.append(f"<div class='health-title'><span class='owner-tag {html.escape(owner)}'>{html.escape(owner)}</span></div>")
        parts.append("<div class='health-signals'>")
        parts.append(f"<div class='signal'><span class='signal-label'>最近活动</span><span class='signal-value'>{ago_str}</span></div>")
        parts.append(f"<div class='signal'><span class='signal-label'>事件数</span><span class='signal-value'>{info['event_count']}</span></div>")
        parts.append(f"<div class='signal'><span class='signal-label'>最近错误</span><span class='signal-value'>{info['error_count']}</span></div>")
        parts.append("</div>")
        _between_flip_faces(parts)
        if conn:
            back = query_health_back(conn, owner, days)
            _render_health_back(parts, owner, info, back)
        _close_flip_card(parts)
    parts.append("</div></div>")


def _render_active_section(parts: list, active_data: dict, sessions_maps: dict, paired_maps: dict, days: int, conn, owner_filter: str = ""):
    parts.append("<details class='section collapsible' data-default-open open>")
    parts.append(f"<summary class='section-head'><span class='collapse-chevron'></span><h2>{LABELS['active_usage']}</h2>"
                 "<span class='meta'>总次数 / 会话 / 配对率 / 目录归属</span></summary>")
    parts.append("<div class='active-grid'>")
    for etype, title in CATEGORIES:
        rows = active_data.get(etype, [])
        sessions_map = sessions_maps.get(etype, {})
        paired_map = paired_maps.get(etype, {})
        _open_flip_card(parts, "active-card")
        parts.append(f"<div class='active-head'><span class='active-title'>{html.escape(title)}</span>"
                     f"<span class='active-count'>{len(rows)} 个</span></div>")
        if not rows:
            parts.append(f"<div class='empty-note'>{LABELS['none']}</div>")
        for name, scope, count, path, owner in rows:
            key = (name, scope or "")
            sess_n = sessions_map.get(key, 0)
            meta_parts = []
            if sess_n:
                meta_parts.append(f"{sess_n} 会话")
            meta_str = " · ".join(meta_parts)
            badge_html = ""
            if etype in PAIRABLE_READ_TYPES:
                paired_n, pairable_total = paired_map.get(key, (0, 0))
                if pairable_total > 0:
                    cls = "good" if paired_n == pairable_total else ("mid" if paired_n > 0 else "bad")
                    badge_html = f"<span class='badge {cls}'>{paired_n}/{pairable_total} 配对</span>"
            name_html = _file_link(name or "", path)
            owner_tip = f" data-tip='{html.escape(path)}'" if path else ""
            owner_html = f"<span class='owner-tag {html.escape(owner)}'{owner_tip}>{html.escape(owner)}</span>"
            parts.append(
                f"<div class='row' data-owner='{html.escape(owner)}'>"
                f"<span class='num'>{count}</span>"
                f"<span class='name'>{name_html}</span>"
                f"<span class='meta'>{meta_str}</span>"
                f"{badge_html}"
                f"{owner_html}"
                f"</div>"
            )
        _between_flip_faces(parts)
        # 計算背面數據 + 渲染 (跟隨 owner_filter)
        agg = query_etype_aggregate(conn, etype, days, owner_filter)
        _render_active_back(parts, etype, title, agg, days, owner_filter)
        _close_flip_card(parts)
    parts.append("</div></details>")


def _sort_cold_by_section(items: list, section_def: dict, last_seen_maps: dict) -> list:
    """按最久未触发排序, 已禁用的排最后."""
    ls_map = last_seen_maps[section_def["event_type"]]
    ls_key_fn = section_def["last_seen_key_fn"]
    active = [i for i in items if not i.get("disabled")]
    disabled = [i for i in items if i.get("disabled")]
    def sort_key(item):
        ts = ls_map.get(ls_key_fn(item), "")
        return (0, "") if not ts else (1, ts)
    return sorted(active, key=sort_key) + disabled


def _make_cold_name_fmt(section_def: dict, ls_map: dict):
    """构造 cold section 的 name_fmt 闭包."""
    ls_key_fn = section_def["last_seen_key_fn"]
    archive_type = section_def.get("archive_type", "") if section_def.get("supports_archive") else ""
    def fmt(item):
        last = fmt_last_seen(ls_map.get(ls_key_fn(item), ""))
        scope = item.get("scope", "") if section_def.get("supports_archive") else ""
        return cold_row_with_owner(
            item["name"], item["path"], item["owner"], last,
            archive_type=archive_type, archive_scope=scope,
            disabled=item.get("disabled", False),
        )
    return fmt


def _render_cold_section(parts: list, cold_data_by_id: dict, last_seen_maps: dict, overridden_user: set):
    parts.append("<details class='section collapsible' data-default-open open>")
    parts.append(f"<summary class='section-head'><span class='collapse-chevron'></span><h2>{LABELS['cold_candidates']}</h2>"
                 "<span class='meta'>最近时间窗口内 0 触发的对象，建议清理或合并</span></summary>")
    parts.append("<div class='cold-grid'>")
    for section_def in COLD_SECTIONS:
        data = cold_data_by_id[section_def["id"]]
        data["cold"] = _sort_cold_by_section(data["cold"], section_def, last_seen_maps)
        ls_map = last_seen_maps[section_def["event_type"]]
        render_risk(
            parts,
            section_def["label_key"],
            data["cold"],
            data["universe_count"],
            name_fmt=_make_cold_name_fmt(section_def, ls_map),
            universe=data.get("universe", []),
        )
    if overridden_user:
        names_str = ", ".join(sorted(overridden_user))
        parts.append(
            f"<div class='notice'>ⓘ 同名 user 版本被 project 覆盖（已隐藏未计入）: "
            f"<b>{html.escape(names_str)}</b></div>"
        )
    parts.append("</div></details>")


def _render_claude_md_legend(parts: list):
    parts.append(
        "<div class='legend'>"
        "<span class='legend-group'><b>热度</b>"
        "<span class='heat-tag heat-hot'>热</span>"
        "<span class='heat-tag heat-warm'>温</span>"
        "<span class='heat-tag heat-cold'>冷</span>"
        "<span class='heat-tag heat-warn'>纪律</span>"
        "</span>"
        "<span class='legend-group'><b>删减收益</b> (hover 看详情)"
        "<span class='prune-dot prune-high'>高</span>"
        "<span class='prune-dot prune-mid'>中</span>"
        "<span class='prune-dot prune-low'>低</span>"
        "</span>"
        "</div>"
    )


def _render_claude_md_panel(parts: list, claude_analyses: list):
    _init_tiktoken()
    parts.append("<div class='section'>")
    parts.append(f"<div class='section-head'><h2>{LABELS['claude_md_analysis']}</h2>"
                 f"<span class='meta'>token 算法: {html.escape(_TIKTOKEN_STATUS)}</span></div>")
    _render_claude_md_legend(parts)
    parts.append("<div class='claude-md-grid'>")
    if not claude_analyses:
        parts.append(f"<div class='empty-note'>{EMPTY_STATES['no_data']}</div>")
    for a in claude_analyses:
        prunable_tokens = sum(s["tokens"] for s in a["sections"] if s["prune_bucket"] == "prune-high")
        reviewable_tokens = sum(s["tokens"] for s in a["sections"] if s["prune_bucket"] == "prune-mid")
        saveable_pct = int(100 * prunable_tokens / max(a["total_tokens"], 1))
        _open_flip_card(parts, "claude-md-card")
        parts.append(
            f"<div class='claude-md-head'>"
            f"<span class='claude-md-name'>{html.escape(a['display_name'])}</span>"
            f"<span class='claude-md-total'>{a['total_tokens']} token · {len(a['sections'])} 节</span>"
            f"</div>"
        )
        if prunable_tokens > 0 or reviewable_tokens > 0:
            parts.append(
                f"<div class='claude-md-suggest'>"
                f"🔴 高删减收益 ~{prunable_tokens} tok ({saveable_pct}%) · "
                f"🟡 可审查 ~{reviewable_tokens} tok"
                f"</div>"
            )
        parts.append("<ul class='claude-md-sections'>")
        for s in a["sections"]:
            heat_label = {"hot": "热", "warm": "温", "cold": "冷", "warn": "纪律"}.get(s["heat"], "")
            bucket = s["prune_bucket"]
            bucket_label_short = {"prune-high": "高", "prune-mid": "中", "prune-low": "低"}.get(bucket, "")
            level_cls = f"sec-l{s['level']}"
            discipline_note = " · 含纪律关键词" if s.get('has_discipline') else ""
            prune_tooltip = (
                f"删减收益: {bucket_label_short} ({s['prune_score']:.0f})"
                f" · token: {s['token_score']} ({s['tokens']} tok)"
                f" · stale: {s['stale_score']} (加权 hit {s['hit_weighted']})"
                f" · keep: {s['keep_score']:.0f}"
                f"{discipline_note}"
            )
            heading_prefix = "  " if s["level"] == 3 else ""
            heat_cls = s["heat"]
            heading_tip = html.escape(s.get("preview", ""))
            parts.append(
                f"<li class='sec-{heat_cls} {level_cls} {bucket}'>"
                f"<span class='heat-tag heat-{heat_cls}'>{heat_label}</span>"
                f"<span class='prune-dot prune-{bucket.replace('prune-','')}' "
                f"data-tip='{html.escape(prune_tooltip)}'>"
                f"<span>{s['prune_score']:.0f}</span></span>"
                f"<span class='sec-heading'><span class='sec-heading-text' data-tip='{heading_tip}'>{heading_prefix}{html.escape(s['heading'])}</span></span>"
                f"<span class='sec-tokens'>{s['tokens']} token</span>"
                f"</li>"
            )
        parts.append("</ul>")
        _between_flip_faces(parts)
        _render_claude_md_back(parts, a)
        _close_flip_card(parts)
    parts.append("</div></div>")


def _read_file_preview(path: str, limit: int = 600) -> str:
    """讀取檔案首段內容做為 hover 預覽. 失敗返回空."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = f.read(limit + 200)
        data = data.strip()
        if len(data) > limit:
            data = data[:limit] + "…"
        return data
    except Exception:
        return ""


_SUMMARY_CACHE = {}

def _has_chinese(s: str) -> bool:
    """檢測字符串是否包含中文."""
    return any('\u4e00' <= c <= '\u9fff' for c in s)


def _file_summary(path: str, limit: int = 280) -> str:
    """提取檔案的簡短摘要, 優先中文.
    順序: frontmatter description (若含中文) → body 首段中文 → frontmatter description (英文) → body 首段任意."""
    if not path or not os.path.isfile(path):
        return ""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return ""
    cached = _SUMMARY_CACHE.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(4096)
    except Exception:
        return ""

    front_desc = ""
    body_start = 0
    # 解析 YAML frontmatter
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            body_start = end + 4
            front = text[3:end]
            for line in front.splitlines():
                line = line.strip()
                if line.lower().startswith("description:"):
                    front_desc = line[len("description:"):].strip().strip('"').strip("'")
                    break

    # 取 body 首段非 heading 非空白
    body_first = ""
    body_first_zh = ""
    body_text = text[body_start:] if body_start else text
    paragraph_buf = []
    for raw in body_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("---") or line.startswith("```"):
            if paragraph_buf:
                merged = " ".join(paragraph_buf)
                if not body_first:
                    body_first = merged
                if _has_chinese(merged) and not body_first_zh:
                    body_first_zh = merged
                    break
                paragraph_buf = []
            continue
        paragraph_buf.append(line)
    if paragraph_buf and not body_first_zh:
        merged = " ".join(paragraph_buf)
        if not body_first:
            body_first = merged
        if _has_chinese(merged):
            body_first_zh = merged

    # 優先順序: 中文 frontmatter > 中文 body > 英文 frontmatter > 任意 body
    if _has_chinese(front_desc):
        summary = front_desc
    elif body_first_zh:
        summary = body_first_zh
    elif front_desc:
        summary = front_desc
    else:
        summary = body_first

    if len(summary) > limit:
        summary = summary[:limit] + "…"
    _SUMMARY_CACHE[path] = (mtime, summary)
    return summary


def _compute_memory_stats(items: list, with_size: bool) -> dict:
    """Memory/Compact 統計: 數量 + 總大小 + 最舊 + 按類型分."""
    stats = {"total": len(items), "total_size": 0, "oldest": "", "type_count": {}}
    if not items:
        return stats
    oldest_mtime = float("inf")
    for row in items:
        if with_size:
            name, path, mtime, size = row
            stats["total_size"] += size
        else:
            name, path, mtime = row
        # 從文件名前綴推類型 (user_xxx / feedback_xxx / project_xxx / reference_xxx)
        prefix = name.split("_", 1)[0] if "_" in name else "其他"
        stats["type_count"][prefix] = stats["type_count"].get(prefix, 0) + 1
        if mtime < oldest_mtime:
            oldest_mtime = mtime
            stats["oldest"] = name
    if oldest_mtime != float("inf"):
        stats["oldest_ts"] = datetime.fromtimestamp(oldest_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return stats


def _render_file_list_panel(parts: list, label_key: str, meta: str, items: list, with_size: bool = False, panel_id: str = "", show_stats: bool = True):
    """通用 Memory/Compact 文件列表渲染 + 統計 sheet 抽屜."""
    parts.append("<div class='section'>")
    pid = panel_id or label_key
    stats = _compute_memory_stats(items, with_size) if show_stats else None
    head_html = f"<div class='section-head'><h2>{LABELS[label_key]}</h2><span class='meta'>{meta}</span>"
    if show_stats:
        head_html += f"<button class='sheet-btn' data-sheet-target='sheet-{pid}'>统计</button>"
    head_html += "</div>"
    parts.append(head_html)
    parts.append("<div class='memory-list'>")
    if not items:
        parts.append(f"<div class='empty-note'>{EMPTY_STATES['no_data']}</div>")
    for row in items[:10]:
        if with_size:
            name, path, mtime, size = row
            extra = f"{size} B"
        else:
            name, path, mtime = row
            extra = ""
        mtime_ts = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        d = days_ago(mtime_ts)
        ago = "今天" if d == 0 else f"{d} 天前"
        preview = _file_preview(path)
        link = _file_link_plain(name, path, tip=preview)
        meta_str = f"{ago} · {extra}" if extra else ago
        parts.append(
            f"<div class='mem-row'>"
            f"<span class='mem-name'>{link}</span>"
            f"<span class='mem-meta'>{meta_str}</span>"
            f"</div>"
        )
    parts.append("</div>")
    # Sheet 內容
    if show_stats:
        parts.append(f"<div class='sheet' id='sheet-{pid}'>")
        parts.append(f"<div class='sheet-head'><h3>{LABELS[label_key]} 统计</h3></div>")
        parts.append("<div class='sheet-body'>")
        parts.append(
            f"<div class='flip-stat-grid'>"
            f"<div class='flip-stat'><span class='flip-stat-label'>总数</span><span class='flip-stat-value accent'>{stats['total']}</span></div>"
        )
        if with_size:
            size_kb = stats["total_size"] / 1024
            parts.append(
                f"<div class='flip-stat'><span class='flip-stat-label'>总空间</span><span class='flip-stat-value'>{size_kb:.1f} KB</span></div>"
            )
        if stats.get("oldest"):
            oldest_disp = fmt_relative_time(stats.get("oldest_ts", "")) if stats.get("oldest_ts") else "—"
            parts.append(
                f"<div class='flip-stat'><span class='flip-stat-label'>最旧文件</span><span class='flip-stat-value' style='font-size:11px'>{html.escape(stats['oldest'])[:24]}</span></div>"
                f"<div class='flip-stat'><span class='flip-stat-label'>距今</span><span class='flip-stat-value'>{oldest_disp}</span></div>"
            )
        parts.append("</div>")
        if stats["type_count"]:
            parts.append("<div class='flip-back-section'><div class='flip-stat-label'>按类型分布</div><div class='owner-dist'>")
            total = sum(stats["type_count"].values()) or 1
            for tname, c in sorted(stats["type_count"].items(), key=lambda x: -x[1]):
                pct = c / total * 100
                parts.append(
                    f"<div class='owner-bar-row'>"
                    f"<span class='type-name'>{html.escape(tname)}</span>"
                    f"<div class='owner-bar'><div class='owner-bar-fill' style='width:{pct:.0f}%'></div></div>"
                    f"<span class='owner-bar-num'>{c}</span>"
                    f"</div>"
                )
            parts.append("</div></div>")
        parts.append("</div>")  # /sheet-body
        parts.append("</div>")  # /sheet
    parts.append("</div>")  # /section


def _render_footer(parts: list):
    parts.append(f"<footer>数据源: SQLite · jsonl 仅作备份 · {LABELS['refresh_hint']}</footer>")
    parts.append("</div>")  # page end
    parts.append("<script src='/app.js'></script>")
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

    # Tab 1: 总览 (Hero + Today + Health) — 完整 hero 含 pills/summary/sparkline
    hero_agg = query_hero_aggregates(conn, days)
    parts.append("<div class='tab-content active' data-tab='overview'>")
    _render_hero(parts, days, owner_filter, total, sessions, total_all, cold_total,
                 this_week, last_week, sparkline_svg, hero_agg)
    _render_today_panel(parts, owner_activity, days, conn)
    _render_health_panel(parts, health, days, conn)
    parts.append("</div>")

    # Tab 2: 工具使用 (time pills + owner filter + Active + Cold)
    parts.append("<div class='tab-content' data-tab='usage'>")
    parts.append("<div class='tab-controls'>")
    parts.append("<div class='control-row'>")
    parts.append("<span class='control-label'>时间范围</span>")
    _render_time_pills(parts, days, owner_filter)
    parts.append("</div>")
    parts.append("<div class='control-row'>")
    parts.append("<span class='control-label'>目录归属</span>")
    _render_owner_filter(parts, ordered_owners, owner_filter)
    parts.append("</div>")
    parts.append("</div>")
    _render_active_section(parts, active_data, sessions_maps, paired_maps, days, conn, owner_filter)
    _render_cold_section(parts, cold_data_by_id, last_seen_maps, overridden_user)
    parts.append("</div>")

    # Tab 3: 上下文 (CLAUDE.md 分析) — 極簡 header, 無 pills/filter
    parts.append("<div class='tab-content' data-tab='context'>")
    _render_claude_md_panel(parts, claude_analyses)
    parts.append("</div>")

    # Tab 4: 记忆 (Memory + Compact) — 極簡 header, 無 pills/filter
    parts.append("<div class='tab-content' data-tab='memory'>")
    _render_file_list_panel(parts, "memory_panel",
                            "按最近修改时间排序, 点击可在 Mac 打开",
                            mem_files, with_size=True, panel_id="memory")
    _render_file_list_panel(parts, "compact_panel",
                            "所有 compact 存档按时间倒序",
                            compact_files, panel_id="compact", show_stats=False)
    parts.append("</div>")

    # Tab 5: 每日AI大事 — 独立 JSON 数据源, 非 events.db
    parts.append("<div class='tab-content' data-tab='news'>")
    _render_news_panel(parts)
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


def _type_name_label(label: str) -> str:
    return f"<span class='type-name'>{html.escape(label)}</span>"


def _render_active_back(parts: list, etype: str, title: str, agg: dict, days: int = 30, owner_filter: str = ""):
    """Active card 背面: 該 type 的聚合分析."""
    spark = render_sparkline(agg["daily"], width=200, height=36) if agg["daily"] else "<div class='sparkline-empty'>无数据</div>"
    last = fmt_relative_time(agg["last_ts"]) if agg["last_ts"] else "—"
    days_n, days_total = agg["day_coverage"]
    sess_n, sess_total = agg["session_coverage"]
    pair_n, pair_total = agg["paired_total"], agg["pairable_total"]
    # 配對率顯示
    if pair_total > 0:
        pair_pct = pair_n / pair_total * 100
        pair_html = f"{pair_n}/{pair_total} <small>({pair_pct:.0f}%)</small>"
    elif etype in PAIRABLE_READ_TYPES:
        pair_html = "—"
    else:
        pair_html = "—<small> 不适用</small>"
    # token tooltip
    tok_tooltip = (
        "估算依据: tiktoken(SKILL.md) × 触发次数 加权\n"
        "误差 ±20%: 缓存复用未计、子文件展开未计\n"
        f"{agg['token_breakdown']}"
    )
    filter_note = f" · {html.escape(owner_filter)}" if owner_filter else ""

    parts.append(_flip_back_title(f"更多分析 · {html.escape(title)}{filter_note}"))
    parts.append(_flip_back_section(f"{days} 天趋势", spark))
    parts.append(_flip_stat_grid([
        _flip_stat("最近触发", last),
        _flip_stat("窗口覆盖", f"{days_n}/{days_total} 天"),
        _flip_stat("会话覆盖", f"{sess_n}/{sess_total}"),
        _flip_stat("配对率", pair_html),
    ]))
    if agg["owner_dist"]:
        parts.append(_flip_back_section("OWNER 分布", _owner_dist_html(agg["owner_dist"], _owner_tag_label, columns=True)))
    parts.append(_flip_back_section(
        "TOKEN 回收估算",
        f"<div class='flip-stat-value accent'>≈ {agg['token_estimate']:,} "
        f"<small data-tip='{html.escape(tok_tooltip)}'>?</small></div>"
    ))


def _render_cold_back(parts: list, label_key: str, progress: dict):
    """Cold card 背面: 進度 + 批量操作."""
    total = progress["total"]
    disabled = progress["disabled"]
    cold_active = progress["cold_active"]
    used = progress["active_used"]
    pct = (disabled / max(total, 1)) * 100
    parts.append(_flip_back_title(f"批量管理 · {LABELS[label_key]}"))
    parts.append(_flip_stat_grid([
        _flip_stat("已禁用", f"{disabled} / {total}", cls="accent"),
        _flip_stat("待处理冷藏", cold_active, cls="warning"),
        _flip_stat("实际使用", used),
        _flip_stat("禁用进度", f"{pct:.0f}%", cls="accent"),
    ]))
    parts.append(_flip_back_section(
        "进度条",
        f"<div class='cold-progress-bar'><div class='cold-progress-fill' style='width:{pct:.0f}%'></div></div>"
    ))
    parts.append(
        f"<div class='flip-actions'>"
        f"<button class='flip-action-btn danger' data-bulk-disable='{html.escape(label_key)}'>一键禁用全部冷藏</button>"
        f"</div>"
    )


def _render_hero_window_back(parts: list, agg: dict, days: int):
    p = agg.get("period", {})
    cur, prev, pct = p.get("current", 0), p.get("previous", 0), p.get("pct_change", 0)
    diff_cls = "accent" if pct >= 0 else "danger"
    sign = "+" if pct >= 0 else ""
    parts.append(_flip_back_title("窗口对比"))
    parts.append(_flip_stat_grid([
        _flip_stat("本窗口", f"{cur:,}", cls="accent"),
        _flip_stat(f"前 {days} 天", f"{prev:,}"),
        _flip_stat("变化", f"{sign}{pct:.0f}%", cls=diff_cls),
        _flip_stat("每日均", f"{cur/max(days,1):.1f}"),
    ]))


def _render_hero_events_back(parts: list, agg: dict):
    breakdown = agg.get("type_breakdown", [])
    parts.append(_flip_back_title("按类型分布"))
    label_of = lambda t: next((l for et, l, _ in EVENT_TYPES if et == t), t)
    parts.append(_owner_dist_html(breakdown, lambda t: _type_name_label(label_of(t)), limit=20))


def _render_hero_sessions_back(parts: list, agg: dict):
    s = agg.get("sessions", {})
    recent = s.get("recent", [])
    avg = s.get("avg_per_session", 0)
    longest = max((r["events"] for r in recent), default=0)
    parts.append(_flip_back_title("会话明细"))
    parts.append(_flip_stat_grid([
        _flip_stat("每会话事件均", f"{avg:.1f}", cls="accent"),
        _flip_stat("最长会话", longest),
    ]))
    if recent:
        rows = []
        for r in recent:
            sid_short = html.escape((r["id"] or "")[:8])
            ts_short = fmt_relative_time(r["ts"]) if r["ts"] else ""
            rows.append(
                f"<div class='session-row'>"
                f"<span class='session-id'>{sid_short}</span>"
                f"<span class='session-events'>{r['events']} 次</span>"
                f"<span class='session-ts'>{ts_short}</span>"
                f"</div>"
            )
        parts.append(_flip_back_section("最近 5 个会话", f"<div class='session-list'>{''.join(rows)}</div>"))


def _render_hero_alltime_back(parts: list, agg: dict):
    a = agg.get("all_time", {})
    total = a.get("total", 0)
    age = a.get("db_age_days", 0)
    first = fmt_relative_time(a.get("first_ts", "")) if a.get("first_ts") else "—"
    monthly = a.get("monthly", [])
    parts.append(_flip_back_title("全期统计"))
    parts.append(_flip_stat_grid([
        _flip_stat("总事件", f"{total:,}", cls="accent"),
        _flip_stat("DB 年龄", f"{age} 天"),
        _flip_stat("首条记录", f"<span style='font-size:11px'>{first}</span>"),
        _flip_stat("日均", f"{total/max(age,1):.1f}"),
    ]))
    if monthly:
        max_m = max(c for _, c in monthly) or 1
        bars = []
        for mon, c in monthly:
            h = (c / max_m) * 100
            empty_cls = " empty" if c == 0 else ""
            bars.append(
                f"<div class='month-bar' title='{mon}: {c} 次'>"
                f"<div class='month-bar-inner'><div class='month-bar-fill{empty_cls}' style='height:{h:.0f}%'></div></div>"
                f"<span class='month-label'>{mon[5:]}</span></div>"
            )
        parts.append(_flip_back_section("近 12 个月", f"<div class='month-bars'>{''.join(bars)}</div>"))


# slot 分派
_HERO_BACK_DISPATCH = {
    "window": _render_hero_window_back,
    "events": lambda parts, agg, days: _render_hero_events_back(parts, agg),
    "sessions": lambda parts, agg, days: _render_hero_sessions_back(parts, agg),
    "all_time": lambda parts, agg, days: _render_hero_alltime_back(parts, agg),
}


def _render_hero_metric_back(parts: list, slot: str, agg: dict, days: int):
    """Hero 4 個 metric 卡的背面."""
    fn = _HERO_BACK_DISPATCH.get(slot)
    if fn:
        fn(parts, agg, days)


def _render_today_back(parts: list, owner: str, back: dict, days: int):
    daily = back.get("daily", [])
    spark = render_sparkline(daily, width=200, height=36) if daily else ""
    type_counts = back.get("type_counts", {})
    last_session = back.get("last_session", "")
    last_ts = back.get("last_ts", "")
    label_of = lambda t: next((l for et, l, _ in EVENT_TYPES if et == t), t)

    parts.append(_flip_back_title(f"{html.escape(owner)} 详情"))
    parts.append(_flip_back_section(f"{days} 天趋势", spark))
    parts.append(_flip_stat_grid([
        _flip_stat("会话数", back.get("session_count", 0), cls="accent"),
        _flip_stat("最后活跃", fmt_relative_time(last_ts) if last_ts else "—"),
    ]))
    if type_counts:
        parts.append(_flip_back_section(
            "按类型拆分",
            _owner_dist_html(type_counts, lambda t: _type_name_label(label_of(t)))
        ))
    if last_session:
        parts.append(_flip_back_section(
            "最近 session",
            f"<div class='session-id-full'>{html.escape(last_session[:16])}</div>"
        ))
    parts.append(
        f"<div class='flip-actions'>"
        f"<a class='flip-action-btn' href='/?days={days}&owner={html.escape(owner)}#usage'>跳到工具使用</a>"
        f"</div>"
    )


def _render_health_back(parts: list, owner: str, info: dict, back: dict):
    hourly = back.get("hourly", [])
    spark = render_sparkline(hourly, width=200, height=36) if hourly else ""
    err_count = info.get("error_count", 0)
    event_count = info.get("event_count", 1)
    err_pct = (err_count / max(event_count, 1)) * 100
    errors = back.get("errors", [])
    err_cls = "danger" if err_pct > 1 else ""

    parts.append(_flip_back_title(f"{html.escape(owner)} 健康详情"))
    parts.append(_flip_back_section("近 24 小时趋势", spark))
    parts.append(_flip_stat_grid([
        _flip_stat("错误占比", f"{err_pct:.1f}%", cls=err_cls),
        _flip_stat("空窗时长", back.get("gap", "—")),
    ]))
    if errors:
        err_rows = "".join(
            f"<div class='error-line'>{html.escape(line[:120])}{'...' if len(line) > 120 else ''}</div>"
            for line in errors
        )
        parts.append(_flip_back_section("最近错误日志", f"<div class='error-log'>{err_rows}</div>"))


def _render_claude_md_back(parts: list, analysis: dict):
    """CLAUDE.md card 背面: 文件總覽 + 複製可刪減清單."""
    agg = query_claude_md_aggregate(analysis)
    name = analysis.get("display_name", "")
    path = analysis.get("path", "")
    parts.append(_flip_back_title(f"文件总览 · {html.escape(name)}"))
    parts.append(_flip_stat_grid([
        _flip_stat("总 token", f"{agg['total_tok']:,}", cls="accent"),
        _flip_stat("段落数", agg["section_count"]),
        _flip_stat("高收益段", f"{agg['high_n']} 段 / {agg['high_tok']:,} tok", cls="danger"),
        _flip_stat("可审查段", f"{agg['mid_n']} 段 / {agg['mid_tok']:,} tok", cls="warning"),
        _flip_stat("含纪律词", f"{agg['discipline']} 段"),
        _flip_stat("可省比例", f"{agg['saveable_pct']}%", cls="accent"),
    ]))
    parts.append(
        f"<div class='flip-actions'>"
        f"<button class='flip-action-btn' data-copy-prune='{html.escape(path)}'>复制可删减清单</button>"
        f"</div>"
    )


# ============================================================
# AI News tab
# ============================================================
def _load_news_data() -> dict:
    """读取 ai-news.json, 失败返回空 payload."""
    import json
    if not os.path.isfile(NEWS_JSON_PATH):
        return {"updated_at": None, "sources": [], "_missing": True}
    try:
        with open(NEWS_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"updated_at": None, "sources": [], "_error": str(e)}


def _load_news_votes() -> dict:
    """读投票数据, 失败返回空 dict. 返回 {url: entry}."""
    import json
    if not os.path.isfile(NEWS_VOTES_PATH):
        return {}
    try:
        with open(NEWS_VOTES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("votes", {}) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _fmt_news_ts(ts: str) -> str:
    """把 ISO 时间字符串转成 '2h ago' / '昨天' 之类相对时间."""
    if not ts:
        return ""
    try:
        # 支持 +00:00 / Z 两种
        t = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(t)
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = (now - dt).total_seconds()
        if diff < 0:
            return "刚刚"
        if diff < 60:
            return f"{int(diff)}s"
        if diff < 3600:
            return f"{int(diff // 60)}m"
        if diff < 86400:
            return f"{int(diff // 3600)}h"
        if diff < 86400 * 7:
            return f"{int(diff // 86400)}d"
        return dt.strftime("%m-%d")
    except Exception:
        return ts[:10] if len(ts) >= 10 else ts


def _fmt_news_publish_time(ts) -> str:
    """精准发布时间, 统一成本地时区 (JST) 'YYYY-MM-DD HH:MM'.

    输入兼容:
    - ISO 8601 带时区: '2026-04-21T03:43:03Z' / '2026-04-22T14:31:47+09:00'
    - 非标准 RSS (ithome): '2026-04-22  11:04:40' (视为本地时区)
    - None / 空串: 返回空串
    """
    if not ts:
        return ""
    raw = str(ts).strip()
    # 尝试 ISO 解析
    try:
        iso = raw.replace("Z", "+00:00")
        # 处理 ithome 的 '2026-04-22  11:04:40' 格式 (双空格, 无 T)
        if "T" not in iso and "+" not in iso and iso.count(":") == 2:
            iso = re.sub(r"\s+", "T", iso, count=1)
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            # 无时区, 当作 UTC (保守)
            dt = dt.replace(tzinfo=timezone.utc)
        # 转本地时区 (Mac 系统 = JST)
        local = dt.astimezone()
        return local.strftime("%Y-%m-%d %H:%M")
    except Exception:
        # fallback: 取前 16 字符
        return raw[:16]


NEWS_VISIBLE_COUNT = 5


def _render_news_item(parts: list, it: dict, source_id: str, votes_by_url: dict, hidden: bool = False):
    """votes_by_url: {url: {"score": "up"|"down"|"star", ...}} — 由 _render_news_panel 传入."""
    title = it.get("title", "").strip() or "(no title)"
    url = it.get("url", "") or "#"
    current_score = (votes_by_url.get(url) or {}).get("score") or ""
    is_voted = current_score in ("up", "star", "down")
    cls = "news-item news-item-hidden" if hidden else "news-item"
    if is_voted:
        cls += f" voted-{current_score}"
    parts.append(f"<li class='{cls}'>")
    # title 行 + 投票按钮组并排
    parts.append("<div class='news-item-row'>")
    parts.append(f"<a class='news-item-title' href='{html.escape(url)}' target='_blank' rel='noopener'>{html.escape(title)}</a>")
    ai_score = it.get("ai_score")
    reason = it.get("reason", "")
    if ai_score is not None:
        parts.append(
            f"<span class='news-item-ai-score' title='{html.escape(reason)}'>"
            f"💡 {ai_score}</span>"
        )
    # 三档反馈按钮: 👎 / 👍 / ⭐. 同一 item 互斥 (后端保存 score 字段).
    parts.append("<span class='news-vote-group'>")
    for score_val, emoji, tip in (
        ("down", "👎", "没兴趣 / 过滤类似内容"),
        ("up", "👍", "一般好 / 标记已读有用"),
        ("star", "⭐", "超赞 / 强信号"),
    ):
        btn_cls = "news-vote-btn"
        if current_score == score_val:
            btn_cls += " voted"
        parts.append(
            f"<button class='{btn_cls}' "
            f"data-vote-url='{html.escape(url)}' "
            f"data-vote-title='{html.escape(title[:160])}' "
            f"data-vote-source='{html.escape(source_id)}' "
            f"data-vote-score='{score_val}' "
            f"title='{tip}'>{emoji}</button>"
        )
    parts.append("</span>")
    parts.append("</div>")
    # meta 行: 仅显示精准发布时间 (本地时区, 无相对时间)
    pub_display = _fmt_news_publish_time(it.get("ts"))
    # 摘要行: 优先 LLM 生成的 summary, fallback 到 RSS desc
    body_text = (it.get("summary") or "").strip() or (it.get("desc") or "").strip()
    if body_text:
        parts.append(f"<div class='news-item-desc'>{html.escape(body_text)}</div>")
    if pub_display:
        parts.append(f"<div class='news-item-meta'>{html.escape(pub_display)}</div>")
    # Opus 分析: 工作区帮助 + Claude 使用. 无论相不相关都显示 (两者无关就显示两行"无相关")
    ws = (it.get("workspace_help") or "").strip() or "无相关"
    cu = (it.get("claude_usage") or "").strip() or "无相关"
    ws_is_na = ws == "无相关"
    cu_is_na = cu == "无相关"
    parts.append("<div class='news-item-analysis'>")
    parts.append(
        f"<div class='news-analysis-row {'na' if ws_is_na else 'rel'}'>"
        f"<span class='news-analysis-label'>工作区</span>"
        f"<span class='news-analysis-text'>{html.escape(ws)}</span>"
        f"</div>"
    )
    parts.append(
        f"<div class='news-analysis-row {'na' if cu_is_na else 'rel'}'>"
        f"<span class='news-analysis-label'>Claude</span>"
        f"<span class='news-analysis-text'>{html.escape(cu)}</span>"
        f"</div>"
    )
    parts.append("</div>")
    if it.get("hn_url") and it.get("url") and it["hn_url"] != it["url"]:
        parts.append(f"<a class='news-item-alt' href='{html.escape(it['hn_url'])}' target='_blank' rel='noopener'>讨论页 ↗</a>")
    parts.append("</li>")


def _render_news_source_card(parts: list, src: dict, votes_by_url: dict):
    """单个新闻源卡片. 首屏显示前 N 条, 余下折叠."""
    sid = src.get("id", "")
    label = src.get("label", sid)
    items = src.get("items", [])
    src_url = src.get("source_url", "")
    updated = _fmt_news_ts(src.get("updated_at", ""))
    err = src.get("error")

    parts.append(f"<div class='news-card' data-source='{html.escape(sid)}'>")
    parts.append("<div class='news-card-head'>")
    parts.append(f"<h3 class='news-card-title'>{html.escape(label)}</h3>")
    parts.append("<div class='news-card-meta'>")
    if updated:
        parts.append(f"<span class='news-meta-ts'>更新 {updated}</span>")
    if src_url:
        parts.append(f"<a class='news-meta-src' href='{html.escape(src_url)}' target='_blank' rel='noopener'>原站 ↗</a>")
    parts.append("</div>")
    parts.append("</div>")

    if err:
        parts.append(f"<div class='news-error'>抓取失败: {html.escape(str(err)[:120])}</div>")
        parts.append("</div>")
        return
    if not items:
        parts.append("<div class='news-empty'>暂无内容</div>")
        parts.append("</div>")
        return

    parts.append("<ol class='news-list'>")
    for i, it in enumerate(items):
        _render_news_item(parts, it, sid, votes_by_url, hidden=(i >= NEWS_VISIBLE_COUNT))
    parts.append("</ol>")
    hidden_count = max(0, len(items) - NEWS_VISIBLE_COUNT)
    if hidden_count > 0:
        parts.append(
            f"<button class='news-expand-btn' data-news-expand='{hidden_count}'>"
            f"展开剩余 {hidden_count} 条</button>"
        )
    parts.append("</div>")


def _render_news_panel(parts: list):
    """每日 AI 大事 tab. 数据来自 ai-news.json (由 fetch-ai-news.py 生成)."""
    data = _load_news_data()
    votes_by_url = _load_news_votes()
    # 兼容老数据: 值是旧的 {ts, title, source} 无 score, 视作 up
    for _u, _v in votes_by_url.items():
        if isinstance(_v, dict) and "score" not in _v:
            _v["score"] = "up"
    voted_urls = set(votes_by_url.keys())
    parts.append("<div class='section'>")
    parts.append("<div class='section-head news-head'>")
    parts.append(f"<h2>{LABELS['news_panel']}</h2>")
    parts.append("<span class='meta'>HN / GitHub Trending / 量子位 / iThome 每日聚合</span>")
    updated_disp = _fmt_news_ts(data.get("updated_at", "")) if data.get("updated_at") else ""
    if updated_disp:
        parts.append(f"<span class='news-global-ts'>数据 {updated_disp}</span>")
    if voted_urls:
        counts = {"down": 0, "up": 0, "star": 0}
        for v in votes_by_url.values():
            s = v.get("score") if isinstance(v, dict) else None
            if s in counts:
                counts[s] += 1
        parts.append(
            f"<span class='news-vote-count'>"
            f"👎 {counts['down']} · 👍 {counts['up']} · ⭐ {counts['star']}</span>"
        )
    stage_map = data.get("stage_by_source", {}) if data else {}
    if stage_map:
        stage_emoji = {"cold": "🥶", "mid": "🌡️", "hot": "🔥"}
        stage_tooltip = {
            "cold": "冷启动: 反馈累计 <10 条, 用原生排序 (HN 分数 / GitHub stars / RSS pubDate), 尚未启用 AI 评分",
            "mid": "中启动: 反馈累计 10-49 条, AI 根据你的点赞偏好打分, 已接近稳定",
            "hot": "热启动: 反馈累计 >=50 条, AI 每累计 20 条新反馈自动演进 source.md 偏好",
        }
        labels = {
            "hackernews": "HN",
            "github_trending": "GitHub",
            "qbitai": "量子位",
            "ithome_tw": "iThome",
        }
        bits = []
        for sid, stage in stage_map.items():
            emoji = stage_emoji.get(stage, "")
            label = labels.get(sid, sid)
            tooltip = stage_tooltip.get(stage, "")
            bits.append(
                f"{label} <span class='news-stage-emoji' "
                f"data-tooltip=\"{html.escape(tooltip)}\">{emoji}</span>"
            )
        if bits:
            parts.append(f"<span class='news-stage-badges'>阶段: {' · '.join(bits)}</span>")
    parts.append("</div>")

    if data.get("_missing"):
        parts.append(
            "<div class='empty-note'>"
            "尚未生成数据. 运行 <code>python3 ~/Desktop/ai-project/hooks/fetch-ai-news.py</code>."
            "</div>"
        )
        parts.append("</div>")
        return
    if data.get("_error"):
        parts.append(f"<div class='news-error'>读取失败: {html.escape(data['_error'])}</div>")
        parts.append("</div>")
        return

    parts.append("<div class='news-grid'>")
    for src in data.get("sources", []):
        _render_news_source_card(parts, src, votes_by_url)
    parts.append("</div>")
    parts.append("</div>")
