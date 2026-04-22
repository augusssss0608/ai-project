"""总览 tab 渲染入口.

内部 leaf 函数 (_render_hero / _render_today_panel / _render_health_panel + 背面 flip)
目前仍在 shared/http/render.py, 本文件作为 tab 入口 + 组装调度.
"""
from shared.http.render import _render_hero, _render_today_panel, _render_health_panel


def render_overview(parts: list, *,
                    days: int, owner_filter: str,
                    total: int, sessions: int, total_all: int, cold_total: int,
                    this_week: int, last_week: int,
                    sparkline_svg: str, hero_agg: dict,
                    owner_activity: dict, health: dict,
                    conn):
    """渲染总览 tab: Hero + Today + Health (3 个主要 panel)."""
    _render_hero(parts, days, owner_filter, total, sessions, total_all,
                 cold_total, this_week, last_week, sparkline_svg, hero_agg)
    _render_today_panel(parts, owner_activity, days, conn)
    _render_health_panel(parts, health, days, conn)
