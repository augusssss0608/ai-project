"""工具使用 tab: 时间 pills + owner filter + Active + Cold sections + flip 背面."""
import html

from shared.infra.core import (
    LABELS, CATEGORIES, COLD_SECTIONS, PAIRABLE_READ_TYPES,
    fmt_relative_time, fmt_last_seen,
    severity_cls, owner_display,
)
from shared.data.queries import (
    query_etype_aggregate, query_cold_progress,
    build_skill_funnel_rows, funnel_status_counts,
)
from shared.http.render import (
    OWNER_PREFERRED,
    render_sparkline, _render_time_pills,
    _open_flip_card, _between_flip_faces, _close_flip_card,
    _flip_stat, _flip_stat_grid, _flip_back_section, _flip_back_title,
    _owner_dist_html, _owner_tag_label,
    _file_link,
)


def render_usage(parts: list, *,
                 days: int, owner_filter: str,
                 overview_days: int, routing_days: int,
                 ordered_owners: list,
                 active_data: dict, cold_data_by_id: dict,
                 sessions_maps: dict, paired_maps: dict,
                 last_seen_maps: dict, overridden_user: set,
                 conn):
    parts.append("<div class='tab-controls'>")
    parts.append("<div class='control-row'>")
    parts.append("<span class='control-label'>时间范围</span>")
    _render_usage_pills(parts, days, owner_filter, overview_days, routing_days)
    parts.append("</div>")
    parts.append("<div class='control-row'>")
    parts.append("<span class='control-label'>目录归属</span>")
    _render_owner_filter(parts, ordered_owners, owner_filter)
    parts.append("</div>")
    parts.append("</div>")
    _render_funnel_section(parts, active_data, sessions_maps, paired_maps,
                            cold_data_by_id, last_seen_maps, owner_filter)
    _render_active_section(parts, active_data, sessions_maps, paired_maps, days, conn, owner_filter)
    _render_cold_section(parts, cold_data_by_id, last_seen_maps, overridden_user)


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


_FUNNEL_STATUS_LABEL = {
    "paired": ("✓", "已配对", "good"),
    "read-only": ("⚠", "读多无动作", "mid"),
    "explicit-only": ("⚠", "调用未读", "mid"),
    "cold": ("·", "长期冷藏", "bad"),
}


def _render_funnel_section(parts, active_data, sessions_maps, paired_maps,
                            cold_data_by_id, last_seen_maps, owner_filter):
    """Skill 触发漏斗：单表 + 状态筛选 chip + 异常优先排序."""
    rows = build_skill_funnel_rows(active_data, sessions_maps, paired_maps,
                                    cold_data_by_id, last_seen_maps)
    counts = funnel_status_counts(rows)
    total = len(rows)

    parts.append("<details class='section collapsible' data-default-open open>")
    parts.append("<summary class='section-head'>"
                 "<span class='collapse-chevron'></span>"
                 "<h2>Skill 触发漏斗</h2>"
                 "<span class='meta'>每个 skill 实际用得怎样</span>"
                 "</summary>")
    parts.append(
        "<p class='section-intro'>"
        "一行一个 skill，看它是 “读了没用”、“点名没配对”，还是长期没人用。"
        "异常项可以考虑改 SKILL.md 或下架。"
        "</p>"
    )

    # 状态筛选 — 复用 .pill 现有筛选体系
    parts.append("<div class='pills funnel-filter' id='funnel-status-filter'>")
    parts.append(f"<a class='pill active' href='#' data-funnel-status=''>全部 <b>{total}</b></a>")
    for st in ("explicit-only", "read-only", "cold", "paired"):
        icon, label, _ = _FUNNEL_STATUS_LABEL.get(st, ("?", st, ""))
        n = counts.get(st, 0)
        parts.append(
            f"<a class='pill' href='#' data-funnel-status='{html.escape(st)}'>"
            f"{html.escape(icon)} {html.escape(label)} <b>{n}</b>"
            f"</a>"
        )
    parts.append("</div>")

    if not rows:
        parts.append("<div class='empty-note'>(无 skill 数据)</div>")
        parts.append("</details>")
        return

    # 紧凑双行列表（不再用表格）
    parts.append("<ul class='funnel-list'>")
    for r in rows:
        st = r["status"]
        icon, label, badge_cls = _FUNNEL_STATUS_LABEL.get(st, ("?", st, ""))
        owner = r.get("owner") or "other"
        owner_filter_attr = ""
        if owner_filter and owner_filter != owner:
            owner_filter_attr = " style='display:none'"
        name_html = _file_link(r["name"], r["path"])
        scope_tag = f"<span class='funnel-scope'>{html.escape(r['scope'] or '')}</span>" if r.get("scope") else ""
        owner_html = f"<span class='owner-tag {html.escape(owner)}'>{html.escape(owner_display(owner))}</span>"
        last_seen = r.get("last_seen")
        last_seen_str = fmt_relative_time(last_seen) if last_seen else "(从未)"
        # 配对率
        if r.get("pairable_total"):
            paired_rate_str = f"{r['paired']}/{r['pairable_total']}"
        else:
            paired_rate_str = "—"
        disabled_cls = " disabled-item" if r.get("disabled") else ""
        parts.append(
            f"<li class='funnel-item funnel-row funnel-item-{html.escape(badge_cls)}{disabled_cls}' "
            f"data-funnel-status='{html.escape(st)}' data-owner='{html.escape(owner)}'{owner_filter_attr}>"
            f"<span class='badge {html.escape(badge_cls)} funnel-item-status'>"
            f"{html.escape(icon)} {html.escape(label)}</span>"
            f"<span class='funnel-item-name'>{name_html}</span>"
            f"{scope_tag or '<span class=\"funnel-scope funnel-scope-empty\"></span>'}"
            f"{owner_html}"
            f"<span class='funnel-item-metrics'>"
            f"<span class='m-cell'><i>读</i><b>{r['read']}</b></span>"
            f"<span class='m-cell'><i>调</i><b>{r['explicit']}</b></span>"
            f"<span class='m-cell'><i>会话</i><b>{r['sessions']}</b></span>"
            f"<span class='m-cell m-paired'><i>配对</i><b>{html.escape(paired_rate_str)}</b></span>"
            f"</span>"
            f"<span class='funnel-item-last'>最近 {html.escape(last_seen_str)}</span>"
            f"</li>"
        )
    parts.append("</ul>")
    parts.append("</details>")


def cold_row_with_owner(
    name_text: str, path: str, owner: str, last_seen_str: str = "",
    archive_type: str = "", archive_scope: str = "", disabled: bool = False,
) -> str:
    name_html = _file_link(name_text, path)
    owner_tip = f" data-tip='{html.escape(path)}'" if path else ""
    owner_html = f"<span class='owner-tag {html.escape(owner)}'{owner_tip}>{html.escape(owner_display(owner))}</span>"
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

def _render_active_section(parts: list, active_data: dict, sessions_maps: dict, paired_maps: dict, days: int, conn, owner_filter: str = ""):
    # skill_read / skill_explicit 已被触发漏斗覆盖，跳过避免重复
    SKIP_ACTIVE = {"skill_read", "skill_explicit"}
    parts.append("<details class='section collapsible' data-default-open open>")
    parts.append(f"<summary class='section-head'><span class='collapse-chevron'></span><h2>{LABELS['active_usage']}</h2>"
                 "<span class='meta'>总次数 / 会话 / 配对率 / 目录归属</span></summary>")
    parts.append("<div class='active-grid'>")
    for etype, title in CATEGORIES:
        if etype in SKIP_ACTIVE:
            continue
        rows = active_data.get(etype, [])
        sessions_map = sessions_maps.get(etype, {})
        paired_map = paired_maps.get(etype, {})
        _open_flip_card(parts, "active-card")
        parts.append(f"<div class='active-head'><span class='active-title'>{html.escape(title)}</span>"
                     f"<span class='active-count'><b>{len(rows)}</b>项</span></div>")
        parts.append("<div class='active-rows'>")
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
            owner_html = f"<span class='owner-tag {html.escape(owner)}'{owner_tip}>{html.escape(owner_display(owner))}</span>"
            parts.append(
                f"<div class='row' data-owner='{html.escape(owner)}'>"
                f"<span class='num'>{count}</span>"
                f"<span class='name'>{name_html}</span>"
                f"<span class='meta'>{meta_str}</span>"
                f"{badge_html}"
                f"{owner_html}"
                f"</div>"
            )
        parts.append("</div>")  # /.active-rows
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
    # cold_skills / cold_skills_explicit 已被触发漏斗的 "长期冷藏" 状态覆盖，跳过避免重复
    SKIP_COLD = {"cold_skills", "cold_skills_explicit"}
    parts.append("<details class='section collapsible' data-default-open open>")
    parts.append(f"<summary class='section-head'><span class='collapse-chevron'></span><h2>{LABELS['cold_candidates']}</h2>"
                 "<span class='meta'>最近时间窗口内 0 触发的对象，建议清理或合并</span></summary>")
    parts.append("<div class='cold-grid'>")
    for section_def in COLD_SECTIONS:
        if section_def["id"] in SKIP_COLD:
            continue
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
