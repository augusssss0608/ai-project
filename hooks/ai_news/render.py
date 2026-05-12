"""每日 AI 大事 tab 渲染层.

数据来源: ai-news.json (由 ai_news.fetch_debug 或 ai-news-fetch skill 生成).
后端只生产 shell HTML + 嵌入 JSON payload, 前端 (shared/static/app.js) 负责渲染交互.
"""
import html
import json
import os
from datetime import datetime, timezone

from shared.infra.core import LABELS, NEWS_JSON_PATH, NEWS_VOTES_PATH


def _load_news_data() -> dict:
    """读取 ai-news.json, 失败返回空 payload."""
    if not os.path.isfile(NEWS_JSON_PATH):
        return {"updated_at": None, "sources": [], "_missing": True}
    try:
        with open(NEWS_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"updated_at": None, "sources": [], "_error": str(e)}


def _load_news_votes() -> dict:
    """读投票数据, 返回 {url: entry}."""
    if not os.path.isfile(NEWS_VOTES_PATH):
        return {}
    try:
        with open(NEWS_VOTES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("votes", {}) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load_news_favorites() -> dict:
    """读收藏数据, 返回 {url: entry}."""
    if not os.path.isfile(NEWS_VOTES_PATH):
        return {}
    try:
        with open(NEWS_VOTES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("favorites", {}) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _fmt_news_ts(ts: str) -> str:
    """把 ISO 时间字符串转成 '2h' / '昨天' 之类相对时间 (仅用于头部 '数据 Xh' 提示)."""
    if not ts:
        return ""
    try:
        t = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(t)
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = (now - dt).total_seconds()
        if diff < 0:
            return "刚刚"
        if diff < 60:
            return f"{int(diff)}s"
        if diff < 3600:
            return f"{int(diff // 60)}m"
        if diff < 86400:
            return f"{int(diff // 3600)}h"
        if diff < 86400 * 7:
            return f"{int(diff // 86400)}d"
        return dt.strftime("%m-%d")
    except Exception:
        return ts[:10] if len(ts) >= 10 else ts


def render_news(parts: list):
    """渲染每日 AI 大事 tab 内容 (不含 <div class='tab-content'> 包裹)."""
    data = _load_news_data()
    votes_by_url = _load_news_votes()
    voted_urls = set(votes_by_url.keys())

    parts.append("<div class='section'>")
    parts.append("<div class='section-head news-head'>")
    parts.append(f"<h2>{LABELS['news_panel']}</h2>")
    parts.append("<span class='meta'>HN / GitHub Trending / 量子位 / iThome 每日聚合</span>")
    updated_disp = _fmt_news_ts(data.get("updated_at", "")) if data.get("updated_at") else ""
    if updated_disp:
        parts.append(f"<span class='news-global-ts'>数据 {updated_disp}</span>")
    if voted_urls:
        counts = {"down": 0, "up": 0, "star": 0}
        for v in votes_by_url.values():
            s = v.get("score")
            if s in counts:
                counts[s] += 1
        parts.append(
            f"<span class='news-vote-count'>"
            f"👎 {counts['down']} · 👍 {counts['up']} · ⭐ {counts['star']}</span>"
        )
    fav_total = len(_load_news_favorites())
    parts.append(
        f"<button class='news-mode-toggle' type='button' data-mode-current='sources' "
        f"aria-label='切换收藏视图'>❤️ 收藏 <b class='fav-count'>{fav_total}</b></button>"
    )
    parts.append("</div>")

    if data.get("_missing"):
        parts.append(
            "<div class='empty-note'>"
            "尚未生成数据. 运行 <code>python3 ~/Desktop/ai-project/hooks/ai_news/fetch_debug.py</code>."
            "</div>"
        )
        parts.append("</div>")
        return
    if data.get("_error"):
        parts.append(f"<div class='news-error'>读取失败: {html.escape(data['_error'])}</div>")
        parts.append("</div>")
        return

    sources = data.get("sources", [])
    favorites_by_url = _load_news_favorites()
    payload = {
        "sources": sources,
        "stage_by_source": data.get("stage_by_source", {}),
        "votes": votes_by_url,
        "favorites": favorites_by_url,
        # 新增 #2/#5 输出（向后兼容：旧数据无这两段时前端走 fallback）
        "featured_items": data.get("featured_items", []),
        "pipeline_metrics": data.get("pipeline_metrics", {}),
    }
    payload_json = json.dumps(payload, ensure_ascii=False)
    payload_json = payload_json.replace("</", "<\\/")
    parts.append(f"<script id='news-data' type='application/json'>{payload_json}</script>")

    parts.append("<div class='news-reader' data-news-reader>")
    parts.append("  <aside class='news-src-list' id='news-src-list'></aside>")
    parts.append("  <section class='news-view'>")
    parts.append("    <div class='news-slide-viewport' id='news-viewport'>")
    parts.append("      <div class='news-slide-track' id='news-track'></div>")
    parts.append("    </div>")
    parts.append("    <nav class='news-pagination' id='news-pagination'></nav>")
    parts.append("  </section>")
    parts.append("</div>")
    parts.append("</div>")  # close .section
