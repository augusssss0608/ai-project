"""上下文 tab: CLAUDE.md 分析面板."""
import html

from shared.infra.core import (
    LABELS, EMPTY_STATES,
    _init_tiktoken, _TIKTOKEN_STATUS,
)
from shared.data.queries import query_claude_md_aggregate
from shared.http.render import (
    _open_flip_card, _between_flip_faces, _close_flip_card,
    _flip_back_title,
    _flip_stat, _flip_stat_grid,
)


def render_context(parts: list, *, claude_analyses: list):
    _render_claude_md_panel(parts, claude_analyses)


def _render_claude_md_legend(parts: list):
    parts.append(
        "<div class='legend'>"
        "<span class='legend-group'><b>热度</b>"
        "<span class='heat-tag heat-hot'>热</span>"
        "<span class='heat-tag heat-warm'>温</span>"
        "<span class='heat-tag heat-cold'>冷</span>"
        "<span class='heat-tag heat-warn'>纪律</span>"
        "</span>"
        "<span class='legend-group'><b>删减收益</b> (hover 看详情)"
        "<span class='prune-dot prune-high'>高</span>"
        "<span class='prune-dot prune-mid'>中</span>"
        "<span class='prune-dot prune-low'>低</span>"
        "</span>"
        "</div>"
    )

def _render_claude_md_panel(parts: list, claude_analyses: list):
    _init_tiktoken()
    parts.append("<div class='section'>")
    parts.append(f"<div class='section-head'><h2>{LABELS['claude_md_analysis']}</h2>"
                 f"<span class='meta'>token 算法: {html.escape(_TIKTOKEN_STATUS)}</span></div>")
    _render_claude_md_legend(parts)
    parts.append("<div class='claude-md-grid'>")
    if not claude_analyses:
        parts.append(f"<div class='empty-note'>{EMPTY_STATES['no_data']}</div>")
    for a in claude_analyses:
        prunable_tokens = sum(s["tokens"] for s in a["sections"] if s["prune_bucket"] == "prune-high")
        reviewable_tokens = sum(s["tokens"] for s in a["sections"] if s["prune_bucket"] == "prune-mid")
        saveable_pct = int(100 * prunable_tokens / max(a["total_tokens"], 1))
        _open_flip_card(parts, "claude-md-card")
        parts.append(
            f"<div class='claude-md-head'>"
            f"<span class='claude-md-name'>{html.escape(a['display_name'])}</span>"
            f"<span class='claude-md-total'>{a['total_tokens']} token · {len(a['sections'])} 节</span>"
            f"</div>"
        )
        if prunable_tokens > 0 or reviewable_tokens > 0:
            parts.append(
                f"<div class='claude-md-suggest'>"
                f"🔴 高删减收益 ~{prunable_tokens} tok ({saveable_pct}%) · "
                f"🟡 可审查 ~{reviewable_tokens} tok"
                f"</div>"
            )
        parts.append("<ul class='claude-md-sections'>")
        for s in a["sections"]:
            heat_label = {"hot": "热", "warm": "温", "cold": "冷", "warn": "纪律"}.get(s["heat"], "")
            bucket = s["prune_bucket"]
            bucket_label_short = {"prune-high": "高", "prune-mid": "中", "prune-low": "低"}.get(bucket, "")
            level_cls = f"sec-l{s['level']}"
            discipline_note = " · 含纪律关键词" if s.get('has_discipline') else ""
            prune_tooltip = (
                f"删减收益: {bucket_label_short} ({s['prune_score']:.0f})"
                f" · token: {s['token_score']} ({s['tokens']} tok)"
                f" · stale: {s['stale_score']} (加权 hit {s['hit_weighted']})"
                f" · keep: {s['keep_score']:.0f}"
                f"{discipline_note}"
            )
            heading_prefix = "  " if s["level"] == 3 else ""
            heat_cls = s["heat"]
            heading_tip = html.escape(s.get("preview", ""))
            parts.append(
                f"<li class='sec-{heat_cls} {level_cls} {bucket}'>"
                f"<span class='heat-tag heat-{heat_cls}'>{heat_label}</span>"
                f"<span class='prune-dot prune-{bucket.replace('prune-','')}' "
                f"data-tip='{html.escape(prune_tooltip)}'>"
                f"<span>{s['prune_score']:.0f}</span></span>"
                f"<span class='sec-heading'><span class='sec-heading-text' data-tip='{heading_tip}'>{heading_prefix}{html.escape(s['heading'])}</span></span>"
                f"<span class='sec-tokens'>{s['tokens']} token</span>"
                f"</li>"
            )
        parts.append("</ul>")
        _between_flip_faces(parts)
        _render_claude_md_back(parts, a)
        _close_flip_card(parts)
    parts.append("</div></div>")

def _render_claude_md_back(parts: list, analysis: dict):
    """CLAUDE.md card 背面: 文件總覽 + 複製可刪減清單."""
    agg = query_claude_md_aggregate(analysis)
    name = analysis.get("display_name", "")
    path = analysis.get("path", "")
    parts.append(_flip_back_title(f"文件总览 · {html.escape(name)}"))
    parts.append(_flip_stat_grid([
        _flip_stat("总 token", f"{agg['total_tok']:,}", cls="accent"),
        _flip_stat("段落数", agg["section_count"]),
        _flip_stat("高收益段", f"{agg['high_n']} 段 / {agg['high_tok']:,} tok", cls="danger"),
        _flip_stat("可审查段", f"{agg['mid_n']} 段 / {agg['mid_tok']:,} tok", cls="warning"),
        _flip_stat("含纪律词", f"{agg['discipline']} 段"),
        _flip_stat("可省比例", f"{agg['saveable_pct']}%", cls="accent"),
    ]))
    parts.append(
        f"<div class='flip-actions'>"
        f"<button class='flip-action-btn' data-copy-prune='{html.escape(path)}'>复制可删减清单</button>"
        f"</div>"
    )


# ============================================================
# AI News tab
# ============================================================
# 每日 AI 大事 tab 渲染已迁到 ai_news.render (保持低耦合, 数据层模块在 ai_news.data)
