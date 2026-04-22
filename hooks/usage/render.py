"""工具使用 tab 渲染入口."""
from shared.http.render import (
    _render_time_pills, _render_owner_filter,
    _render_active_section, _render_cold_section,
)


def render_usage(parts: list, *,
                 days: int, owner_filter: str,
                 ordered_owners: list,
                 active_data: dict, cold_data_by_id: dict,
                 sessions_maps: dict, paired_maps: dict,
                 last_seen_maps: dict, overridden_user: set,
                 conn):
    """渲染工具使用 tab: 时间 pills + owner filter + Active 区 + Cold 区."""
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
