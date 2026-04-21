"""新闻抓取函数. 每个函数接受 params dict (来自 fetcher.yaml), 返回 items list.

items 每条包含: title, url, desc, ts (ISO), 以及源特有字段 (HN: score/comments, GH: today_stars_int/lang).
"""
import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser

TIMEOUT = 12
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) claude-code-dashboard/2.0"
JINA_READER_PREFIX = "https://r.jina.ai/"


def _fetch(url: str, headers=None, timeout=TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def fetch_hn_algolia(params: dict) -> list:
    """HN Algolia API. params:
    - query: 关键词 (用于本地 re 过滤)
    - sort_by: 'points' | 'comments' | 'created_at'
    - time_window_hours: int
    - min_points: int
    - limit: int (候选上限)
    """
    import re as _re
    query = params.get("query", "")
    sort_by = params.get("sort_by", "points")
    window = int(params.get("time_window_hours", 48))
    min_points = int(params.get("min_points", 30))
    limit = int(params.get("limit", 20))

    all_hits = {}
    # 1) front_page
    url1 = "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=50"
    try:
        for h in json.loads(_fetch(url1)).get("hits", []):
            all_hits[h.get("objectID")] = h
    except Exception:
        pass
    # 2) 最近 N 小时按分数降序
    since = int(datetime.now(timezone.utc).timestamp()) - 3600 * window
    url2 = (
        f"https://hn.algolia.com/api/v1/search?tags=story"
        f"&numericFilters=points%3E{min_points},created_at_i%3E{since}&hitsPerPage=50"
    )
    try:
        for h in json.loads(_fetch(url2)).get("hits", []):
            all_hits[h.get("objectID")] = h
    except Exception:
        pass

    # 本地 keyword 过滤
    kw_re = _re.compile(query.replace(" OR ", "|").replace(" ", r"\s*"), _re.I) if query else None
    items = []
    for h in all_hits.values():
        title = (h.get("title") or h.get("story_title") or "").strip()
        if not title:
            continue
        if kw_re and not kw_re.search(title):
            continue
        items.append({
            "title": title,
            "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
            "hn_url": f"https://news.ycombinator.com/item?id={h.get('objectID')}",
            "score": int(h.get("points", 0) or 0),
            "comments": int(h.get("num_comments", 0) or 0),
            "ts": h.get("created_at", ""),
            "author": h.get("author", ""),
            "desc": "",
        })
    # sort
    key_map = {
        "points": lambda x: x["score"],
        "comments": lambda x: x["comments"],
        "created_at": lambda x: x["ts"],
    }
    items.sort(key=key_map.get(sort_by, key_map["points"]), reverse=True)
    return items[:limit]
