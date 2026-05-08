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
        "<span class='meta'>每个会话跨了哪些子项目</span>"
        "</div>"
    )
    parts.append(
        "<p class='section-intro'>"
        "一行 = 一次 Claude 会话。色块代表读到的子项目，灰色代表没读到。"
        "本应跨项目却只读一边时，可能是路由漏了；点行看完整事件时间线。"
        f"（最近 {len(session_routes)} 个 session / {days} 天窗口）"
        "</p>"
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
    # 只看命中的 owner（按 event 数排序）
    owner_dist = sess["owner_distribution"] or {}
    hit_owners = sorted(owner_dist.items(), key=lambda kv: -kv[1])
    owners_count = len(hit_owners)
    total_events = sess["event_count"] or 1

    # 默认展开
    parts.append("<details class='routing-session' open>")
    parts.append("<summary class='routing-summary'>")
    parts.append(
        f"<span class='routing-time'>{html.escape(last_seen_str)}</span>"
        f"<span class='routing-duration'>{html.escape(duration_str)}</span>"
        f"<span class='routing-events'>{sess['event_count']} 事件</span>"
    )

    # owner 比例 bar（按 event 数分段染色，仅命中）
    parts.append("<div class='routing-owner-vis'>")
    parts.append("<div class='routing-bar'>")
    for owner, count in hit_owners:
        pct = (count / total_events) * 100
        if pct < 0.5:
            continue
        parts.append(
            f"<span class='routing-bar-segment owner-{html.escape(owner)}' "
            f"style='width:{pct:.1f}%'></span>"
        )
    parts.append("</div>")
    # 命中 owner 列表（仅命中，标签不可点击）
    parts.append("<div class='routing-owner-chips'>")
    for owner, count in hit_owners:
        pct = (count / total_events) * 100
        parts.append(
            f"<span class='owner-tag {html.escape(owner)}'>"
            f"{html.escape(owner)} <b>{pct:.0f}%</b></span>"
        )
    parts.append("</div>")
    parts.append("</div>")

    # 跨 owner 数（弱提示）
    parts.append(
        f"<span class='routing-cross-count'>"
        f"<b>{owners_count}</b> 个项目"
        f"</span>"
    )
    parts.append("</summary>")

    # 展开事件时间线
    _render_session_timeline(parts, sess)
    parts.append("</details>")


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
        "<th>+offset</th><th>event</th><th>owner</th>"
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
            f"<td class='routing-event-cell'>"
            f"<span class='routing-type-prefix'>{html.escape(type_label)}</span>"
            f"{name_html}"
            f"</td>"
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
