"""上下文 tab 渲染入口 (CLAUDE.md 分析)."""
from shared.http.render import _render_claude_md_panel


def render_context(parts: list, *, claude_analyses: list):
    """渲染 CLAUDE.md 分析面板."""
    _render_claude_md_panel(parts, claude_analyses)
