"""路由 tab：Owner 路由足迹（Phase 3.3）

每个 session 一行：时间 / 跨度 / 事件数 / owner 色块序列 / 展开事件时间线
取代旧的"上下文"段级 prune_score 面板。
"""
import html

from shared.infra.core import (
    fmt_relative_time, fmt_local_time,
)
from shared.data.queries import (
    ROUTING_OWNER_ORDER, fmt_duration,
)
from shared.http.render import _file_link_plain


# 路由 tab 主入口
def render_context(parts: list, *, session_routes: list, days: int = 30):
    parts.append("<div class='section'>")
    parts.append(
        "<div class='section-head'>"
        "<h2>Session 路由足迹</h2>"
        f"<span class='meta'>最近 {len(session_routes)} 个 session（{days} 天窗口） · 点击行展开事件时间线</span>"
        "</div>"
    )

    if not session_routes:
        parts.append("<div class='empty-note'>(无 session 数据)</div>")
        parts.append("</div>")
        return

    # 表头说明
    parts.append("<div class='routing-list'>")
    for sess in session_routes:
        _render_session_row(parts, sess, days)
    parts.append("</div>")
    parts.append("</div>")


def _render_session_row(parts: list, sess: dict, days: int):
    sess_id_short = (sess["session_id"] or "")[:8]
    last_seen_str = fmt_relative_time(sess["last_ts"]) or sess["last_ts"]
    duration_str = fmt_duration(sess["duration_seconds"])
    owners_count = len(sess["owners_involved"])

    parts.append("<details class='routing-session'>")
    parts.append("<summary class='routing-summary'>")
    parts.append(
        f"<span class='routing-time'>{html.escape(last_seen_str)}</span>"
        f"<span class='routing-duration'>{html.escape(duration_str)}</span>"
        f"<span class='routing-events'>{sess['event_count']} 事件</span>"
    )

    # owner 色块序列（5 个固定 + 其它追加）
    parts.append("<span class='routing-owners'>")
    for owner in ROUTING_OWNER_ORDER:
        count = sess["owner_distribution"].get(owner, 0)
        if count > 0:
            parts.append(_render_owner_chip(owner, count, days, hit=True))
        else:
            parts.append(_render_owner_chip(owner, 0, days, hit=False))
    # 其它 owner（builtin / global / unknown 等）
    extras = [o for o in sess["owners_involved"] if o not in ROUTING_OWNER_ORDER]
    for owner in extras:
        count = sess["owner_distribution"].get(owner, 0)
        parts.append(_render_owner_chip(owner, count, days, hit=True, secondary=True))
    parts.append("</span>")

    # 跨 owner 数（弱提示）
    parts.append(f"<span class='routing-cross-count'>跨 {owners_count} owner</span>")
    parts.append(f"<span class='routing-session-id' data-tip='{html.escape(sess['session_id'])}'>"
                 f"{html.escape(sess_id_short)}…</span>")
    parts.append("</summary>")

    # 展开事件时间线
    _render_session_timeline(parts, sess)
    parts.append("</details>")


def _render_owner_chip(owner: str, count: int, days: int, hit: bool, secondary: bool = False) -> str:
    cls = "routing-owner-chip"
    if hit:
        cls += " hit"
    else:
        cls += " miss"
    if secondary:
        cls += " secondary"
    cls += f" owner-{html.escape(owner)}"
    label = html.escape(owner)
    count_html = f"<b>{count}</b>" if hit and count > 0 else ""
    if hit:
        # 跳到 usage tab，按 owner 筛选
        href = f"/?days={int(days)}&owner={html.escape(owner)}#usage"
        return (
            f"<a class='{cls}' href='{href}' "
            f"data-tip='跳转到 工具使用 tab，按 {label} 筛选'>"
            f"{label}{count_html}</a>"
        )
    return f"<span class='{cls}' aria-disabled='true'>{label}</span>"


def _render_session_timeline(parts: list, sess: dict):
    parts.append("<div class='routing-timeline'>")
    if sess.get("truncated_count", 0):
        parts.append(
            f"<div class='routing-truncated-note'>"
            f"⚠️ 此 session 共 {sess['event_count']} 事件，超过单 session 上限。"
            f"展示前 50 + 后 50，省略中间 {sess['truncated_count']} 条"
            f"</div>"
        )
    if not sess["events"]:
        parts.append("<div class='empty-note'>(无事件)</div>")
        parts.append("</div>")
        return

    # 计算每个 event 相对 first_ts 的偏移
    parts.append("<table class='routing-timeline-table'>")
    parts.append(
        "<thead><tr>"
        "<th>+offset</th><th>type</th><th>name</th><th>owner</th>"
        "</tr></thead><tbody>"
    )
    first_ts_unix = _ts_to_unix(sess["first_ts"])
    for ev in sess["events"]:
        ts_unix = _ts_to_unix(ev["ts"])
        offset = ts_unix - first_ts_unix if (ts_unix and first_ts_unix) else 0
        offset_str = fmt_duration(offset) if offset > 0 else "0s"
        type_label = ev["type"]
        owner = ev.get("owner") or "unknown"
        name_html = _file_link_plain(ev["name"] or type_label, ev["path"]) if ev["name"] else f"<span class='routing-name-faint'>{html.escape(type_label)}</span>"
        parts.append(
            f"<tr class='routing-event routing-event-{html.escape(type_label)}'>"
            f"<td class='routing-offset'>{html.escape(offset_str)}</td>"
            f"<td class='routing-type'><code>{html.escape(type_label)}</code></td>"
            f"<td class='routing-name'>{name_html}</td>"
            f"<td><span class='owner-tag {html.escape(owner)}'>{html.escape(owner)}</span></td>"
            f"</tr>"
        )
    parts.append("</tbody></table>")
    parts.append("</div>")


def _ts_to_unix(ts_iso: str) -> int:
    """ISO UTC 字符串 → unix 秒"""
    if not ts_iso:
        return 0
    from datetime import datetime, timezone
    try:
        # 容忍带毫秒
        ts = ts_iso.rstrip("Z")
        if "." in ts:
            ts = ts.split(".", 1)[0]
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        return 0
