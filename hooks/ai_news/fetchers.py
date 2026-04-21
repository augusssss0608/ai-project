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


GITHUB_TRENDING_URL_TPL = "https://github.com/trending?since={since}"


class _TrendingParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self._cur = None
        self._capture = None
        self._buf = []
        self._in_article = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        if tag == "article" and "Box-row" in cls:
            self._in_article = True
            self._cur = {"title": "", "url": "", "desc": "", "lang": "",
                         "stars": "", "today_stars": "", "today_stars_int": 0}
            return
        if not self._in_article:
            return
        if tag == "h2":
            self._capture = "h2"
        elif self._capture == "h2" and tag == "a" and a.get("href"):
            href = a["href"].strip()
            if href.startswith("/"):
                self._cur["url"] = "https://github.com" + href
        elif tag == "p" and "col-9" in cls:
            self._capture = "desc"; self._buf = []
        elif tag == "span" and a.get("itemprop") == "programmingLanguage":
            self._capture = "lang"; self._buf = []
        elif tag == "a" and "Link--muted" in cls and "/stargazers" in a.get("href", ""):
            self._capture = "stars"; self._buf = []
        elif tag == "span" and "float-sm-right" in cls:
            self._capture = "today"; self._buf = []

    def handle_data(self, data):
        if not self._in_article or not self._capture:
            return
        if self._capture == "h2":
            self._cur["title"] += data
        else:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if not self._in_article:
            return
        if self._capture == "h2" and tag == "h2":
            self._cur["title"] = re.sub(r"\s+", "", self._cur["title"])
            self._capture = None
        elif self._capture == "desc" and tag == "p":
            self._cur["desc"] = "".join(self._buf).strip()
            self._capture = None; self._buf = []
        elif self._capture == "lang" and tag == "span":
            self._cur["lang"] = "".join(self._buf).strip()
            self._capture = None; self._buf = []
        elif self._capture == "stars" and tag == "a":
            self._cur["stars"] = "".join(self._buf).strip()
            self._capture = None; self._buf = []
        elif self._capture == "today" and tag == "span":
            ts = "".join(self._buf).strip()
            self._cur["today_stars"] = ts
            m = re.search(r"\d+", ts.replace(",", ""))
            self._cur["today_stars_int"] = int(m.group()) if m else 0
            self._capture = None; self._buf = []
        elif tag == "article" and self._in_article:
            if self._cur and self._cur["title"]:
                self.items.append(self._cur)
            self._in_article = False
            self._cur = None
            self._capture = None
            self._buf = []


def fetch_github_trending(params: dict) -> list:
    since = params.get("since", "daily")
    limit = int(params.get("limit", 20))
    url = GITHUB_TRENDING_URL_TPL.format(since=since)
    raw = _fetch(url).decode("utf-8", errors="ignore")
    p = _TrendingParser()
    p.feed(raw)
    items = []
    for it in p.items[:limit]:
        items.append({
            "title": it["title"],
            "url": it["url"],
            "desc": (it["desc"] or "")[:200],
            "ts": _now_iso(),
            "lang": it["lang"],
            "stars": it["stars"],
            "today_stars": it["today_stars"],
            "today_stars_int": it["today_stars_int"],
        })
    items.sort(key=lambda x: x["today_stars_int"], reverse=True)
    return items


def _parse_rss2(xml_bytes: bytes, max_items: int = 20) -> list:
    """通用 RSS 2.0 <channel><item> 解析. 返回 [{title,url,desc,ts,author}]."""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    root = ET.fromstring(xml_bytes)
    channel = root.find("channel")
    out = []
    if channel is None:
        return out
    for it in channel.findall("item"):
        title = (it.findtext("title") or "").strip()
        if not title:
            continue
        link = (it.findtext("link") or "").strip()
        desc = re.sub(r"<[^>]+>", "", (it.findtext("description") or "").strip()).strip()
        creator_el = it.find("{http://purl.org/dc/elements/1.1/}creator")
        author = creator_el.text.strip() if creator_el is not None and creator_el.text else ""
        pub = (it.findtext("pubDate") or "").strip()
        try:
            ts = parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat(timespec="seconds")
        except Exception:
            ts = pub
        out.append({
            "title": title,
            "url": link,
            "desc": desc[:140],
            "ts": ts,
            "author": author,
        })
        if len(out) >= max_items:
            break
    return out


def fetch_rss(params: dict) -> list:
    """通用 RSS 抓取. params:
    - url: RSS 地址
    - time_window_hours: 只保留这个窗口内的条目 (按 pubDate)
    - limit: 最多返回多少条
    """
    url = params["url"]
    window = int(params.get("time_window_hours", 48))
    limit = int(params.get("limit", 15))
    raw = _fetch(url)
    items = _parse_rss2(raw, max_items=max(50, limit * 2))

    cutoff = datetime.now(timezone.utc) - timedelta(hours=window)
    kept = []
    for it in items:
        try:
            ts_dt = datetime.fromisoformat(it["ts"].replace("Z", "+00:00"))
            if ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=timezone.utc)
            if ts_dt >= cutoff:
                kept.append(it)
        except Exception:
            kept.append(it)
    return kept[:limit]


ARTICLE_TIMEOUT = 30
ARTICLE_MAX_CHARS = 6000


def fetch_article_text(url: str) -> tuple:
    """用 Jina Reader 抓文章正文. 返回 (text, err_str).
    text 去掉图片 md / 压缩空行, 截取到 ARTICLE_MAX_CHARS."""
    if not url or not url.startswith(("http://", "https://")):
        return "", "invalid url"
    jina_url = JINA_READER_PREFIX + url
    try:
        raw = _fetch(jina_url, timeout=ARTICLE_TIMEOUT).decode("utf-8", errors="replace")
        raw = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw[:ARTICLE_MAX_CHARS].strip(), ""
    except urllib.error.HTTPError as e:
        return "", f"jina http {e.code}"
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"


_TYPE_DISPATCH = {
    "hn_algolia": fetch_hn_algolia,
    "github_trending": fetch_github_trending,
    "rss": fetch_rss,
}


def fetch_one(source_id: str, fetcher_yaml: dict) -> dict:
    """对单个源执行抓取. 返回 {id, label, source_url, items, error, updated_at}."""
    t = fetcher_yaml.get("type", "")
    params = fetcher_yaml.get("params", {})
    fn = _TYPE_DISPATCH.get(t)
    if fn is None:
        return {"id": source_id, "items": [], "error": f"unknown type: {t}", "updated_at": _now_iso()}
    try:
        items = fn(params)
        return {"id": source_id, "items": items, "error": None, "updated_at": _now_iso()}
    except Exception as e:
        return {"id": source_id, "items": [], "error": f"{type(e).__name__}: {e}",
                "updated_at": _now_iso()}


def fetch_all(sources_config: list) -> list:
    """并行 (ThreadPoolExecutor) 抓取所有源.
    sources_config 每项: {id, label, source_url, fetcher: {type, params}}
    返回: [{id, label, source_url, items, error, updated_at}, ...]
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    results = {s["id"]: None for s in sources_config}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(fetch_one, s["id"], s["fetcher"]): s for s in sources_config}
        for fut in as_completed(futs):
            s = futs[fut]
            res = fut.result()
            res["label"] = s.get("label", s["id"])
            res["source_url"] = s.get("source_url", "")
            results[s["id"]] = res
    return [results[s["id"]] for s in sources_config]
