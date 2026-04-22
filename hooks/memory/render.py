"""记忆 tab 渲染入口 (Memory + Compact 文件列表)."""
from shared.http.render import _render_file_list_panel


def render_memory(parts: list, *, mem_files: list, compact_files: list):
    """渲染 Memory + Compact 文件列表两个面板."""
    _render_file_list_panel(
        parts, "memory_panel",
        "按最近修改时间排序, 点击可在 Mac 打开",
        mem_files, with_size=True, panel_id="memory",
    )
    _render_file_list_panel(
        parts, "compact_panel",
        "所有 compact 存档按时间倒序",
        compact_files, panel_id="compact", show_stats=False,
    )
