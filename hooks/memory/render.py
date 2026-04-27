"""记忆 tab: Memory + Compact 文件列表 panel."""
import html
import os
from datetime import datetime, timezone

from shared.infra.core import LABELS, EMPTY_STATES, days_ago, fmt_relative_time
from shared.http.render import _file_link_plain


def _file_preview(path: str, limit: int = 500) -> str:
    """读取文件原文前 N 字符作为 tooltip 预览, 跳过 YAML frontmatter."""
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(4096)
    except Exception:
        return ""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            text = text[end + 4:]
    text = text.lstrip()
    if len(text) > limit:
        text = text[:limit] + "…"
    return text

def _compute_memory_stats(items: list, with_size: bool) -> dict:
    """Memory/Compact 統計: 數量 + 總大小 + 最舊 + 按類型分."""
    stats = {"total": len(items), "total_size": 0, "oldest": "", "type_count": {}}
    if not items:
        return stats
    oldest_mtime = float("inf")
    for row in items:
        if with_size:
            name, path, mtime, size = row
            stats["total_size"] += size
        else:
            name, path, mtime = row
        # 從文件名前綴推類型 (user_xxx / feedback_xxx / project_xxx / reference_xxx)
        prefix = name.split("_", 1)[0] if "_" in name else "其他"
        stats["type_count"][prefix] = stats["type_count"].get(prefix, 0) + 1
        if mtime < oldest_mtime:
            oldest_mtime = mtime
            stats["oldest"] = name
    if oldest_mtime != float("inf"):
        stats["oldest_ts"] = datetime.fromtimestamp(oldest_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return stats

def _render_file_list_panel(parts: list, label_key: str, meta: str, items: list, with_size: bool = False, panel_id: str = "", show_stats: bool = True):
    """通用 Memory/Compact 文件列表渲染 + 統計 sheet 抽屜."""
    parts.append("<div class='section'>")
    pid = panel_id or label_key
    stats = _compute_memory_stats(items, with_size) if show_stats else None
    total = len(items)
    head_html = (
        f"<div class='section-head'>"
        f"<h2>{LABELS[label_key]}</h2>"
        f"<span class='section-count'><b>{total}</b> 项</span>"
        f"<span class='meta'>{meta}</span>"
    )
    if show_stats:
        head_html += f"<button class='sheet-btn' data-sheet-target='sheet-{pid}'>统计</button>"
    head_html += "</div>"
    parts.append(head_html)
    parts.append("<div class='memory-list'>")
    if not items:
        parts.append(f"<div class='empty-note'>{EMPTY_STATES['no_data']}</div>")
    for row in items:
        if with_size:
            name, path, mtime, size = row
            extra = f"{size} B"
        else:
            name, path, mtime = row
            extra = ""
        mtime_ts = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        d = days_ago(mtime_ts)
        ago = "今天" if d == 0 else f"{d} 天前"
        preview = _file_preview(path)
        link = _file_link_plain(name, path, tip=preview)
        meta_str = f"{ago} · {extra}" if extra else ago
        parts.append(
            f"<div class='mem-row'>"
            f"<span class='mem-name'>{link}</span>"
            f"<span class='mem-meta'>{meta_str}</span>"
            f"</div>"
        )
    parts.append("</div>")
    # Sheet 內容
    if show_stats:
        parts.append(f"<div class='sheet' id='sheet-{pid}'>")
        parts.append(f"<div class='sheet-head'><h3>{LABELS[label_key]} 统计</h3></div>")
        parts.append("<div class='sheet-body'>")
        parts.append(
            f"<div class='flip-stat-grid'>"
            f"<div class='flip-stat'><span class='flip-stat-label'>总数</span><span class='flip-stat-value accent'>{stats['total']}</span></div>"
        )
        if with_size:
            size_kb = stats["total_size"] / 1024
            parts.append(
                f"<div class='flip-stat'><span class='flip-stat-label'>总空间</span><span class='flip-stat-value'>{size_kb:.1f} KB</span></div>"
            )
        if stats.get("oldest"):
            oldest_disp = fmt_relative_time(stats.get("oldest_ts", "")) if stats.get("oldest_ts") else "—"
            parts.append(
                f"<div class='flip-stat'><span class='flip-stat-label'>最旧文件</span><span class='flip-stat-value' style='font-size:11px'>{html.escape(stats['oldest'])[:24]}</span></div>"
                f"<div class='flip-stat'><span class='flip-stat-label'>距今</span><span class='flip-stat-value'>{oldest_disp}</span></div>"
            )
        parts.append("</div>")
        if stats["type_count"]:
            parts.append("<div class='flip-back-section'><div class='flip-stat-label'>按类型分布</div><div class='owner-dist'>")
            total = sum(stats["type_count"].values()) or 1
            for tname, c in sorted(stats["type_count"].items(), key=lambda x: -x[1]):
                pct = c / total * 100
                parts.append(
                    f"<div class='owner-bar-row'>"
                    f"<span class='type-name'>{html.escape(tname)}</span>"
                    f"<div class='owner-bar'><div class='owner-bar-fill' style='width:{pct:.0f}%'></div></div>"
                    f"<span class='owner-bar-num'>{c}</span>"
                    f"</div>"
                )
            parts.append("</div></div>")
        parts.append("</div>")  # /sheet-body
        parts.append("</div>")  # /sheet
    parts.append("</div>")  # /section


def render_memory(parts: list, *, mem_files: list, compact_files: list):
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
