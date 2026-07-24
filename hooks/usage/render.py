"""工具使用 tab: 概览表 + 内嵌可展开 funnel + 状态过滤（F 方案）."""
import html

from shared.infra.core import (
    LABELS, owner_display, fmt_relative_time,
)
from shared.data.queries import (
    build_funnel_rows_by_category, build_overview_summary,
    query_spark_series_maps,
)
from shared.http.render import (
    _file_link,
)


_STATUS_LABEL = {
    "paired": ("✓", "已配对 / 在用", "good"),
    "read-only": ("⚠", "读多无动作", "mid"),
    "explicit-only": ("⚠", "调用未读", "mid"),
    "cold": ("·", "长期冷藏", "cold"),
    "disabled": ("⊘", "停用", "cold"),
}

# spark SVG 配色对应 badge_cls
_SPARK_COLOR = {
    "good": "var(--success)",
    "mid":  "var(--warning)",
    "cold": "var(--text-faint)",
}


def _spark_svg(series: list, color: str, *, w: int = 200, h: int = 26) -> str:
    """生成 30 天柱状 sparkline。空序列返回灰底占位。"""
    n = len(series) if series else 30
    if n == 0:
        n = 30
    max_v = max(series) if series else 0
    bar_w = (w - (n - 1) * 2) / n
    bars = []
    for i in range(n):
        v = series[i] if i < len(series) else 0
        bh = (v / max_v) * (h - 2) if max_v > 0 else 0
        x = i * (bar_w + 2)
        y = h - bh
        opacity = "0.18" if v == 0 else "1"
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
            f'height="{max(1, bh):.1f}" fill="{color}" opacity="{opacity}"/>'
        )
    return (
        f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" '
        f'class="spark-svg" aria-hidden="true">{"".join(bars)}</svg>'
    )


def render_usage(parts: list, *,
                 days: int, owner_filter: str,
                 overview_days: int, routing_days: int,
                 active_data: dict, cold_data_by_id: dict,
                 sessions_maps: dict, paired_maps: dict,
                 last_seen_maps: dict, overridden_user: set,
                 conn):
    parts.append("<div class='tab-controls'>")
    parts.append("<div class='control-row'>")
    parts.append("<span class='control-label'>时间范围</span>")
    _render_usage_pills(parts, days, owner_filter, overview_days, routing_days)
    if owner_filter:
        clear_url_parts = [f"days={overview_days}", f"usage_days={days}",
                           f"routing_days={routing_days}", "tab=usage"]
        clear_url = "/?" + "&".join(clear_url_parts)
        parts.append(
            f"<a class='owner-active-chip' href='{clear_url}'>"
            f"筛选: <b>{html.escape(owner_filter)}</b>"
            f"<span class='owner-active-clear'>✕</span>"
            f"</a>"
        )
    parts.append("</div>")
    parts.append("</div>")

    series_maps = query_spark_series_maps(conn)
    rows_by_cat = build_funnel_rows_by_category(
        active_data, sessions_maps, paired_maps, last_seen_maps, cold_data_by_id,
        series_maps=series_maps,
    )
    summary = build_overview_summary(rows_by_cat)
    _render_overview_section(parts, summary=summary, rows_by_cat=rows_by_cat,
                              owner_filter=owner_filter,
                              overridden_user=overridden_user)


def _render_usage_pills(parts: list, current: int, owner_filter: str,
                         overview_days: int, routing_days: int):
    """工具使用 tab 独立 pills（控制 ?usage_days=N，保留 days / routing_days）。"""
    parts.append("<div class='pills time-pills'>")
    for d in [1, 7, 30, 90, 365]:
        label = "1天" if d == 1 else "7天" if d == 7 else "30天" if d == 30 else "90天" if d == 90 else "1年"
        url_parts = [f"days={overview_days}", f"usage_days={d}",
                     f"routing_days={routing_days}", "tab=usage"]
        if owner_filter:
            url_parts.append(f"owner={html.escape(owner_filter)}")
        url = "/?" + "&".join(url_parts)
        cls = "pill active" if d == current else "pill"
        parts.append(f"<a class='{cls}' href='{url}'>{label}</a>")
    parts.append("</div>")


def _render_overview_section(parts: list, *, summary: list, rows_by_cat: dict,
                              owner_filter: str, overridden_user: set):
    """F 方案：状态 chip + 概览表（每行一个类别）+ 内嵌可展开 funnel 列表."""
    # 统计跨类别状态总数（用于顶部 chip 计数）
    total_counts = {"paired": 0, "read-only": 0, "explicit-only": 0, "cold": 0, "disabled": 0}
    grand_total = 0
    for s in summary:
        grand_total += s["total"]
        total_counts["paired"] += s["paired"]
        total_counts["read-only"] += s["read_only"]
        total_counts["explicit-only"] += s["explicit_only"]
        total_counts["cold"] += s["cold"]
        total_counts["disabled"] += s["disabled"]

    parts.append("<details class='section collapsible' data-default-open open>")
    parts.append("<summary class='section-head'>"
                 "<span class='collapse-chevron'></span>"
                 "<h2>概览 · 触发健康度</h2>"
                 "<span class='meta'>每类一行，点击展开详情；状态 chip / 表头数字可全局过滤</span>"
                 "</summary>")

    # 状态过滤 chips
    parts.append("<div class='pills funnel-filter' id='overview-status-filter'>")
    parts.append(f"<a class='pill active' href='#' data-funnel-status=''>全部 <b>{grand_total}</b></a>")
    for st in ("explicit-only", "read-only", "cold", "paired", "disabled"):
        icon, label, _cls = _STATUS_LABEL.get(st, ("?", st, ""))
        n = total_counts.get(st, 0)
        parts.append(
            f"<a class='pill' href='#' data-funnel-status='{html.escape(st)}'>"
            f"{html.escape(icon)} {html.escape(label)} <b>{n}</b>"
            f"</a>"
        )
    parts.append("</div>")

    # 概览表
    parts.append("<table class='overview-table' id='overview-table'>")
    parts.append("<thead><tr>"
                 "<th class='th-kind'>类型</th>"
                 "<th class='th-num'>总数</th>"
                 "<th class='th-num th-used'>用过</th>"
                 "<th class='th-num th-cold'>冷藏</th>"
                 "<th class='th-num'>配对率</th>"
                 "<th class='th-last'>最近触发</th>"
                 "</tr></thead>")
    parts.append("<tbody>")
    for s in summary:
        kind = s["kind"]
        last_str = fmt_relative_time(s["last_seen"]) if s["last_seen"] else "—"
        parts.append(
            f"<tr class='ov-summary-row' data-kind='{html.escape(kind)}' "
            f"data-paired='{s['paired']}' data-read-only='{s['read_only']}' "
            f"data-explicit-only='{s['explicit_only']}' data-cold='{s['cold']}' "
            f"data-disabled='{s['disabled']}'>"
            f"<td class='ov-kind'><span class='ov-chevron'>▶</span>"
            f"<span class='ov-kind-label'>{html.escape(s['label'])}</span></td>"
            f"<td class='ov-num'>{s['total']}</td>"
            f"<td class='ov-num ov-clickable' data-jump-status='paired'>{s['used']}</td>"
            f"<td class='ov-num ov-clickable ov-num-cold' data-jump-status='cold'>{s['cold']}</td>"
            f"<td class='ov-num'>{html.escape(s['pair_rate_str'])}</td>"
            f"<td class='ov-last'>{html.escape(last_str)}</td>"
            f"</tr>"
        )
        # 详情行（默认隐藏）
        rows = rows_by_cat.get(kind, []) or []
        parts.append(
            f"<tr class='ov-detail-row' data-kind='{html.escape(kind)}' style='display:none'>"
            f"<td colspan='6' class='ov-detail-cell'>"
        )
        if rows:
            _render_category_funnel(parts, kind, rows, owner_filter)
        else:
            parts.append("<div class='empty-note'>(此类别无数据)</div>")
        parts.append("</td></tr>")
    parts.append("</tbody></table>")

    if overridden_user:
        names_str = ", ".join(sorted(overridden_user))
        parts.append(
            f"<div class='notice'>ⓘ 同名 user 版本被 project 覆盖（已隐藏未计入）: "
            f"<b>{html.escape(names_str)}</b></div>"
        )
    parts.append("</details>")


def _render_category_funnel(parts: list, kind: str, rows: list, owner_filter: str):
    """单类别的 sparkline 列表（嵌在概览展开行里）."""
    # 列头（可排序的列加 sortable 标记 + 三角；30 天趋势不可排序）
    parts.append(f"<div class='spark-header' data-kind='{html.escape(kind)}'>"
                 "<div class='sortable' data-sort='status'>状态<span class='sort-ind'>⇅</span></div>"
                 "<div class='sortable' data-sort='name'>名字<span class='sort-ind'>⇅</span></div>"
                 "<div class='sortable' data-sort='owner'>OWNER<span class='sort-ind'>⇅</span></div>"
                 "<div class='h-spark'>30 天趋势</div>"
                 "<div class='sortable h-num' data-sort='total'>总次数<span class='sort-ind'>⇅</span></div>"
                 "<div class='sortable h-last' data-sort='last'>最近触发<span class='sort-ind'>⇅</span></div>"
                 "<div class='h-detail'></div>"
                 "</div>")
    parts.append(f"<ul class='spark-list funnel-list ov-funnel' data-kind='{html.escape(kind)}'>")
    for orig_idx, r in enumerate(rows):
        st = r["status"]
        icon, label, badge_cls = _STATUS_LABEL.get(st, ("?", st, ""))
        owner = r.get("owner") or "other"
        owner_attr = f" data-owner='{html.escape(owner)}'"
        owner_hidden = " style='display:none'" if (owner_filter and owner_filter != owner) else ""
        name_html = _file_link(r["name"], r["path"])
        owner_html = (
            f"<span class='owner-tag owner-filter-trigger {html.escape(owner)}' "
            f"data-owner-filter='{html.escape(owner)}' role='button' tabindex='0'>"
            f"{html.escape(owner_display(owner))}</span>"
        )
        last_str = fmt_relative_time(r.get("last_seen")) if r.get("last_seen") else "(从未)"
        total = r.get("total", 0)
        total_cls = "cold" if total == 0 else (badge_cls if badge_cls in ("good", "mid") else "")
        color = _SPARK_COLOR.get(badge_cls, "var(--text-faint)")
        spark_html = _spark_svg(r.get("series") or [], color)
        paired_str = f"{r['paired']}/{r['pairable_total']}" if r.get("pairable_total") else "—"
        disabled_cls = " disabled-item" if r.get("disabled") else ""
        # 详细面板（默认隐藏，点击按钮展开）— 单行 4 指标紧凑条
        detail_html = (
            f"<div class='spark-detail-pop'>"
            f"<span class='dt-cell'><i>读</i><b>{r['read']}</b></span>"
            f"<span class='dt-sep'></span>"
            f"<span class='dt-cell'><i>调</i><b>{r['explicit']}</b></span>"
            f"<span class='dt-sep'></span>"
            f"<span class='dt-cell'><i>会话</i><b>{r['sessions']}</b></span>"
            f"<span class='dt-sep'></span>"
            f"<span class='dt-cell'><i>配对</i><b>{html.escape(paired_str)}</b></span>"
            f"</div>"
        )
        last_iso = r.get("last_seen") or ""
        # 状态严重度（用于状态列排序：异常优先）
        sev_map = {"explicit-only": 0, "read-only": 1, "cold": 2, "paired": 3, "disabled": 4}
        sev = sev_map.get(st, 9)
        parts.append(
            f"<li class='spark-row funnel-row{disabled_cls}' "
            f"data-funnel-status='{html.escape(st)}'{owner_attr}{owner_hidden} "
            f"data-total='{total}' data-last-ts='{html.escape(last_iso)}' "
            f"data-status-sev='{sev}' data-orig-idx='{orig_idx}' "
            f"data-name='{html.escape(r['name'].lower())}'>"
            f"<span class='badge {html.escape(badge_cls)} spark-status'>"
            f"{html.escape(icon)} {html.escape(label)}</span>"
            f"<span class='spark-name'>{name_html}</span>"
            f"<span class='owner-wrap'>{owner_html}</span>"
            f"<span class='spark-cell'>{spark_html}</span>"
            f"<span class='spark-total {html.escape(total_cls)}'>{total}</span>"
            f"<span class='spark-last'>{html.escape(last_str)}</span>"
            f"<span class='spark-detail-wrap'>"
            f"<button class='spark-detail-btn' type='button'>详细</button>"
            f"{detail_html}"
            f"</span>"
            f"</li>"
        )
    parts.append("</ul>")
