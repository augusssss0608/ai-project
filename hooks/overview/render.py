"""总览 tab: Hero + Today + Health (3 主 panel) + 其 flip 背面渲染."""
import html
from datetime import datetime, timezone

from shared.infra.core import (
    LABELS, EMPTY_STATES, EVENT_TYPES,
    days_ago, fmt_local_time, fmt_relative_time, fmt_pct_change,
)
from shared.data.queries import query_owner_back, query_health_back
from shared.http.render import (
    render_sparkline, _render_time_pills,
    _open_flip_card, _between_flip_faces, _close_flip_card,
    _flip_stat, _flip_stat_grid, _flip_back_section, _flip_back_title,
    _owner_dist_html, _owner_bar_row, _owner_col, _owner_tag_label,
)


def render_overview(parts: list, *,
                    days: int, owner_filter: str,
                    total: int, sessions: int, total_all: int, cold_total: int,
                    this_week: int, last_week: int,
                    sparkline_svg: str, hero_agg: dict,
                    owner_activity: dict, health: dict,
                    conn):
    _render_hero(parts, days, owner_filter, total, sessions, total_all,
                 cold_total, this_week, last_week, sparkline_svg, hero_agg)
    _render_today_panel(parts, owner_activity, days, conn)
    _render_health_panel(parts, health, days, conn)


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
    "window": lambda parts, agg, days: _render_hero_window_back(parts, agg, days),
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

def _type_name_label(label: str) -> str:
    return f"<span class='type-name'>{html.escape(label)}</span>"
