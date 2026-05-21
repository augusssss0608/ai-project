"""每日 AI 大事 tab 渲染层.

数据来源: ai-news.json (由 ai_news.fetch_debug 或 ai-news-fetch skill 生成).
后端只生产 shell HTML + 嵌入 JSON payload, 前端 (shared/static/app.js) 负责渲染交互.
"""
import html
import json
import os
from datetime import datetime, timezone

from shared.infra.core import LABELS, NEWS_JSON_PATH, NEWS_VOTES_PATH

# history.jsonl 与 ai-news.json 同目录 (cloud-sync/),
# 与 ai_news.data.history.HISTORY_PATH 路径定义一致
_HISTORY_PATH = os.path.join(os.path.dirname(NEWS_JSON_PATH), "ai-news-history.jsonl")


def _load_github_first_ts() -> dict:
    """读 history.jsonl, 返回 {url: first_ts} (仅 github_trending 源).

    用于判断 github 条目是否首次出现 (本次 fetch 之前未在 history 里出现过).
    文件不存在或读失败时返回空 dict, 此时所有 github 条目都会被标 is_new.
    """
    if not os.path.isfile(_HISTORY_PATH):
        return {}
    first_ts = {}
    try:
        with open(_HISTORY_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if row.get("source") != "github_trending":
                    continue
                url = row.get("url", "")
                ts = row.get("ts", "")
                if not url or not ts:
                    continue
                cur = first_ts.get(url)
                if cur is None or ts < cur:
                    first_ts[url] = ts
    except Exception:
        return {}
    return first_ts


def _annotate_github_is_new(sources: list, updated_at: str):
    """给 github_trending 源的每个 item 标 is_new:
    history 里没记录过, 或 first_ts >= 本次 updated_at -> True.

    直接 in-place 改写 sources 里的 dict (随后会序列化进 payload_json).
    """
    if not updated_at:
        return
    first_ts_by_url = _load_github_first_ts()
    for src in sources:
        if src.get("id") != "github_trending":
            continue
        for it in src.get("items", []) or []:
            url = it.get("url", "")
            if not url:
                continue
            ft = first_ts_by_url.get(url)
            it["is_new"] = (ft is None) or (ft >= updated_at)


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
    _annotate_github_is_new(sources, data.get("updated_at", ""))
    favorites_by_url = _load_news_favorites()
    payload = {
        "sources": sources,
        "stage_by_source": data.get("stage_by_source", {}),
        "votes": votes_by_url,
        "favorites": favorites_by_url,
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
