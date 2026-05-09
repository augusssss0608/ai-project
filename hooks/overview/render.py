"""总览 tab: Hero (metric strip) + Today · Console Stack (Owner Bay + Event Stream)."""
import html

from shared.infra.core import (
    LABELS, EMPTY_STATES, EVENT_TYPES,
    days_ago, fmt_local_time, fmt_relative_time, owner_display,
)
from shared.http.render import (
    render_sparkline, _render_time_pills, _file_link,
)


def render_overview(parts: list, *,
                    days: int, owner_filter: str,
                    total: int, sessions: int,
                    sparkline_svg: str, spark_meta: dict,
                    hero_agg: dict,
                    owner_activity: dict,
                    owner_dailies: dict,
                    owner_sessions: dict,
                    recent_stream: list,
                    conn,
                    usage_days: int = None,
                    routing_days: int = None):
    _render_hero(parts, days, owner_filter, total, sessions,
                 sparkline_svg, spark_meta, hero_agg,
                 usage_days=usage_days, routing_days=routing_days)
    _render_today_panel(parts, owner_activity, owner_dailies,
                        owner_sessions, recent_stream, days)


def _render_hero(parts: list, days: int, owner_filter: str,
                 total: int, sessions: int,
                 sparkline_svg: str, spark_meta: dict,
                 hero_agg: dict,
                 usage_days: int = None, routing_days: int = None):
    """Hero 区: 顶部 pills + vs prev 对比, 下方 4 列 metric strip (events / sessions / avg / sparkline).
    无外框、无背景、无翻面 — 数据本身即设计."""
    avg = (hero_agg or {}).get("avg_per_session", 0)
    period = (hero_agg or {}).get("period", {})
    pct = period.get("pct_change")

    parts.append("<div class='hero'>")

    # ---- top row: pills 左 + vs prev 右 ----
    parts.append("<div class='hero-top'>")
    _render_time_pills(parts, days, owner_filter,
                       usage_days=usage_days, routing_days=routing_days,
                       anchor="overview")
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


# ============================================================
# Today · Console Stack
# ============================================================
def _render_today_panel(parts: list, owner_activity: dict,
                        owner_dailies: dict, owner_sessions: dict,
                        recent_stream: list, days: int = 7):
    parts.append("<div class='section'>")
    parts.append(
        f"<div class='section-head'><h2>{LABELS['today_panel']}</h2>"
        f"<span class='meta'>· livetail 模式 · 点击 owner 仓位过滤</span></div>"
    )
    parts.append("<div class='console-stack'>")
    _render_owner_bay(parts, owner_activity, owner_dailies, owner_sessions, days)
    _render_event_stream(parts, recent_stream, days)
    parts.append("</div>")  # console-stack
    parts.append("</div>")  # section


def _render_owner_bay(parts: list, owner_activity: dict,
                      owner_dailies: dict, owner_sessions: dict, days: int):
    """上层仓位带：横向排列每个 owner（无卡片框）。"""
    parts.append(f"<div class='owner-bay' data-window='{days}d window'>")

    sorted_owners = sorted(
        owner_activity.items(),
        key=lambda x: -x[1]["event_count"],
    )
    if not sorted_owners:
        parts.append(f"<div class='empty-note'>{EMPTY_STATES['no_events']}</div>")
        parts.append("</div>")
        return

    for owner, info in sorted_owners:
        _render_owner_slot(parts, owner, info,
                           owner_dailies.get(owner, []),
                           owner_sessions.get(owner, 0))
    parts.append("</div>")


def _render_owner_slot(parts: list, owner: str, info: dict,
                       daily: list, session_count: int):
    owner_esc = html.escape(owner)
    owner_label = html.escape(owner_display(owner))

    last_ts = info.get("last_ts", "")
    d_ago = days_ago(last_ts) if last_ts else -1
    if d_ago == 0 and last_ts:
        last_str = fmt_local_time(last_ts) or "今天"
    elif d_ago == 1:
        last_str = f"昨 {fmt_local_time(last_ts) or ''}".strip()
    elif d_ago > 1:
        last_str = f"{d_ago} 天前"
    else:
        last_str = "—"

    spark_svg = render_sparkline(daily, width=120, height=28, with_axis=False) if daily else ""

    parts.append(
        f"<button type='button' class='owner-slot' data-owner='{owner_esc}' "
        f"aria-pressed='false' tabindex='0'>"
        f"<span class='slot-tag'>{owner_label}</span>"
        f"<div class='slot-spark'>{spark_svg}</div>"
        f"<div class='slot-num-row'>"
        f"<span class='slot-num'>{info.get('event_count', 0)}</span>"
        f"<span class='slot-sessions'>{session_count} sess</span>"
        f"</div>"
        f"<span class='slot-time'>{html.escape(last_str)}</span>"
        f"</button>"
    )


def _render_event_stream(parts: list, recent_stream: list, days: int):
    """下层 livetail：所有事件混合按时间倒序。"""
    label_of = lambda t: next((l for et, l, _ in EVENT_TYPES if et == t), t)
    count = len(recent_stream)

    parts.append(
        f"<div class='event-stream' data-count='近 {count} 条 · {days}d 窗口'>"
    )

    if not recent_stream:
        parts.append(
            f"<div class='stream-empty'>{EMPTY_STATES['no_events']}</div>"
        )
    else:
        for ev in recent_stream:
            owner = ev.get("owner") or "other"
            owner_esc = html.escape(owner)
            owner_label = html.escape(owner_display(owner))
            time_str = fmt_local_time(ev.get("ts", "")) or ""
            type_label = label_of(ev.get("type", ""))
            name = ev.get("name", "")
            path = ev.get("path", "")
            name_html = _file_link(name, path) if path and name else html.escape(name or "—")

            parts.append(
                f"<div class='stream-row' data-owner='{owner_esc}'>"
                f"<span class='stream-time'>{html.escape(time_str)}</span>"
                f"<div class='stream-owner'>"
                f"<span class='stream-owner-stripe' aria-hidden='true'></span>"
                f"<span class='stream-owner-tag'>{owner_label}</span>"
                f"</div>"
                f"<span class='stream-type'>{html.escape(type_label)}</span>"
                f"<span class='stream-name'>{name_html}</span>"
                f"<span class='stream-jump'>→ 详情</span>"
                f"</div>"
            )

    parts.append("</div>")  # event-stream

    # footer link 跳工具使用
    parts.append(
        f"<div class='stream-footer'>"
        f"<a href='#usage' class='stream-footer-link'>跳到工具使用 →</a>"
        f"</div>"
    )
