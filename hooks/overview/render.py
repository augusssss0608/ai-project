"""总览 tab: Hero (metric strip) + Today + Today 卡背面渲染."""
import html

from shared.infra.core import (
    LABELS, EMPTY_STATES, EVENT_TYPES,
    days_ago, fmt_local_time, fmt_relative_time,
)
from shared.data.queries import query_owner_back
from shared.http.render import (
    render_sparkline, _render_time_pills,
    _open_flip_card, _between_flip_faces, _close_flip_card,
    _flip_stat, _flip_stat_grid, _flip_back_section, _flip_back_title,
    _owner_dist_html,
)


def render_overview(parts: list, *,
                    days: int, owner_filter: str,
                    total: int, sessions: int,
                    sparkline_svg: str, spark_meta: dict,
                    hero_agg: dict,
                    owner_activity: dict,
                    conn):
    _render_hero(parts, days, owner_filter, total, sessions,
                 sparkline_svg, spark_meta, hero_agg)
    _render_today_panel(parts, owner_activity, days, conn)


def _render_hero(parts: list, days: int, owner_filter: str,
                 total: int, sessions: int,
                 sparkline_svg: str, spark_meta: dict,
                 hero_agg: dict):
    """Hero 区: 顶部 pills + vs prev 对比, 下方 4 列 metric strip (events / sessions / avg / sparkline).
    无外框、无背景、无翻面 — 数据本身即设计."""
    avg = (hero_agg or {}).get("avg_per_session", 0)
    period = (hero_agg or {}).get("period", {})
    pct = period.get("pct_change")

    parts.append("<div class='hero'>")

    # ---- top row: pills 左 + vs prev 右 ----
    parts.append("<div class='hero-top'>")
    _render_time_pills(parts, days, owner_filter)
    if pct is None:
        vs_html = "<span class='delta accent'>新窗口</span>"
    else:
        cls = "up" if pct > 0 else ("down" if pct < 0 else "flat")
        sign = "+" if pct > 0 else ""
        vs_html = f"<span class='delta {cls}'>{sign}{pct:.0f}%</span>"
    parts.append(
        f"<div class='hero-vs'>vs prev {days}d {vs_html}</div>"
    )
    parts.append("</div>")  # hero-top

    parts.append("<div class='hero-rule'></div>")

    # ---- metric strip: 4 cell ----
    parts.append("<div class='hero-strip'>")
    _strip_cell(parts, total, "events", countup=True)
    _strip_cell(parts, sessions, "sessions", countup=True)
    _strip_cell(parts, f"{avg:.1f}", "avg / session")
    _strip_spark(parts, sparkline_svg, spark_meta, days)
    parts.append("</div>")  # hero-strip

    parts.append("</div>")  # hero end


def _strip_cell(parts: list, value, label: str, countup: bool = False):
    parts.append("<div class='hero-cell'>")
    if countup:
        parts.append(f"<div class='hero-num' data-countup='{value}'>0</div>")
    else:
        parts.append(f"<div class='hero-num'>{value}</div>")
    parts.append(f"<div class='hero-cell-label'>{label}</div>")
    parts.append("</div>")


def _strip_spark(parts: list, sparkline_svg: str, meta: dict, days: int):
    parts.append("<div class='hero-cell hero-cell-spark'>")
    if sparkline_svg:
        parts.append(sparkline_svg)
    if meta:
        parts.append(
            f"<div class='hero-spark-meta'>"
            f"<span>{meta['start']}</span>"
            f"<span class='peak'>↑ {meta['peak_val']} ({meta['peak_day']})</span>"
            f"<span>{meta['end']}</span>"
            f"</div>"
        )
    else:
        parts.append(f"<div class='hero-spark-meta'><span>近 {days} 天均无事件</span></div>")
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

def _render_today_back(parts: list, owner: str, back: dict, days: int):
    daily = back.get("daily", [])
    spark = render_sparkline(daily, width=200, height=36) if daily else ""
    type_counts = back.get("type_counts", {})
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
    parts.append(
        f"<div class='flip-actions'>"
        f"<a class='flip-action-btn' href='/?days={days}&owner={html.escape(owner)}#usage'>跳到工具使用</a>"
        f"</div>"
    )

def _type_name_label(label: str) -> str:
    return f"<span class='type-name'>{html.escape(label)}</span>"
