"""新闻抓取函数. 每个函数接受 params dict (来自 fetcher.yaml), 返回 items list.

items 每条包含: title, url, desc, ts (ISO), 以及源特有字段 (HN: score/comments, GH: today_stars_int/lang).
"""
import json
import os
import re
import sys
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

# github.com/trending 是 HTML 页面且无官方 API, 对机房 IP 常年 403; 云端 routine 走 RSSHub
# 取真实 trending 榜单. RSS 只含总 star, 不含"本期新增 star", 故排序改用 trending 名次 (见 *_rank).
RSSHUB_INSTANCES = (
    "https://rsshub.rssforever.com",
    "https://rsshub.app",
)


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


def _parse_int_compact(s: str) -> int:
    """把 GitHub 展示的 '8,069' / '60k' 这种文字 star 数转 int."""
    if not s:
        return 0
    s = s.strip().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*([kKmM]?)", s)
    if not m:
        return 0
    val = float(m.group(1))
    unit = m.group(2).lower()
    if unit == "k":
        val *= 1000
    elif unit == "m":
        val *= 1000000
    return int(val)


def fetch_github_search(params: dict) -> list:
    """GitHub Search API: 按总 star 排序, 找 Claude 生态仓库 (不受 trending 池限制).

    匿名限流 60 次/小时, 每次 pipeline 跑 len(queries) 次请求.
    params:
    - queries: 查询列表 (默认含 claude name/desc/readme + topic:mcp)
    - per_query_limit: 每个 query 取前 N (默认 30, GitHub Search API 上限 100)
    - min_stars: 最低总 star 门槛 (默认 30, 过滤不成熟小项目)
    """
    import urllib.parse as _up
    queries = params.get("queries") or [
        "claude in:name,description,readme",
        "topic:mcp",
    ]
    per_query_limit = int(params.get("per_query_limit", 30))
    min_stars = int(params.get("min_stars", 30))

    # 机房 IP 直连匿名 Search API 常被 403/限流 (总维度长期空的根因).
    # 带 token 时机房 IP 不再被挡, Search 限流 10→30 次/分; 无 token 退回匿名, 行为不变.
    gh_headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        gh_headers["Authorization"] = f"Bearer {token}"

    merged = {}
    errors = []
    for q in queries:
        q_full = f"{q} stars:>={min_stars}"
        url = (
            "https://api.github.com/search/repositories"
            f"?q={_up.quote(q_full)}"
            f"&sort=stars&order=desc&per_page={per_query_limit}"
        )
        try:
            raw = _fetch(url, headers=gh_headers)
            data = json.loads(raw)
        except Exception as e:
            errors.append(f"{type(e).__name__}: {e}")
            continue
        for r in data.get("items", []):
            full_name = r.get("full_name", "")
            html_url = r.get("html_url", "")
            if not full_name or not html_url:
                continue
            if html_url in merged:
                continue
            stars_n = int(r.get("stargazers_count", 0) or 0)
            merged[html_url] = {
                "title": full_name,
                "url": html_url,
                "desc": (r.get("description") or "")[:200],
                "ts": r.get("pushed_at", "") or _now_iso(),
                "lang": r.get("language") or "",
                "stars": f"{stars_n:,}",
                "total_stars_int": stars_n,
                "daily_stars": 0,
                "weekly_stars": 0,
                "monthly_stars": 0,
            }
    # 所有 query 都异常 (限流/403/网络) 而非"查成功但零命中" → 抛出让上层记录到 total 维度错误,
    # 避免机房 IP 被 GitHub 挡后总维度静默返 [].
    if not merged and len(errors) == len(queries):
        raise RuntimeError("github search 全部 query 失败: " + " | ".join(errors))
    return list(merged.values())


def fetch_github_trending_rss(since: str, limit: int = 25) -> list:
    """从 RSSHub 抓 GitHub trending (since = daily/weekly/monthly).

    GitHub 无官方 trending API, HTML 页面对机房 IP 返 403, 故走 RSSHub.
    RSS 条目已按 GitHub trending 名次排序; 只含总 star, 无"本期新增 star".
    返回按名次排列的 list, 每条: {title(full_name), url, desc, ts, lang, stars, total_stars_int}.
    """
    import xml.etree.ElementTree as ET
    path = f"/github/trending/{since}/any"
    raw, last_err = None, None
    for base in RSSHUB_INSTANCES:
        try:
            raw = _fetch(base + path)
            break
        except Exception as e:
            last_err = e
    if raw is None:
        raise last_err or RuntimeError("all RSSHub instances failed")

    root = ET.fromstring(raw)
    items = []
    for node in root.findall(".//item")[:limit]:
        def _text(tag):
            el = node.find(tag)
            return (el.text or "") if el is not None else ""
        title = _text("title").strip()
        url = _text("link").strip()
        if not title or not url:
            continue
        desc_html = _text("description")
        stars_m = re.search(r"Stars:\s*([\d,]+)", desc_html)
        lang_m = re.search(r"Language:\s*([^<\n]+)", desc_html)
        stars_int = _parse_int_compact(stars_m.group(1)) if stars_m else 0
        # 纯描述: 截到 Language: 之前, 去掉 img 和其余标签
        body = re.split(r"Language:", desc_html)[0]
        body = re.sub(r"<img[^>]*>", "", body)
        body = re.sub(r"<[^>]+>", " ", body)
        desc = re.sub(r"\s+", " ", body).strip()
        items.append({
            "title": title,
            "url": url,
            "desc": desc[:200],
            "ts": _now_iso(),
            "lang": lang_m.group(1).strip() if lang_m else "",
            "stars": f"{stars_int:,}",
            "total_stars_int": stars_int,
        })
    return items


def fetch_github_trending_multi(params: dict) -> list:
    """为 daily / weekly / monthly / total 四个维度各产出一个榜单, 返回扁平 list.

    每条 item 带 `dimension` 字段标识所属榜单. 同一仓库可跨维度重复出现 (各维度各留一条).
    daily/weekly/monthly 走 RSSHub trending (真实名次, 见 *_rank); total 走 Search API 按总 star 排.
    单个维度抓取失败不影响其他维度 (各自 try/except); 但四个维度全空时 raise (无论是否抛异常),
    让失败暴露到 source.error, 避免全站被封/限流仍"假装成功"只显示暂无数据.

    params:
    - per_dim_limit: 每维度抓取上限 (默认 25, 前端再截 top N)
    """
    per_dim = int(params.get("per_dim_limit", 25))
    errors = []

    raw_by_url = {}
    dim_urls = {"daily": [], "weekly": [], "monthly": []}
    for since in ("daily", "weekly", "monthly"):
        try:
            sub = fetch_github_trending_rss(since, per_dim)
        except Exception as e:
            errors.append(f"{since}: {type(e).__name__}: {e}")
            sub = []
        for rank, it in enumerate(sub, 1):
            url = it["url"]
            if url not in raw_by_url:
                raw_by_url[url] = {
                    "title": it["title"],
                    "url": url,
                    "desc": it.get("desc", ""),
                    "ts": it.get("ts", ""),
                    "lang": it.get("lang", ""),
                    "stars": it.get("stars", ""),
                    "total_stars_int": it.get("total_stars_int", 0),
                    "daily_stars": 0,
                    "weekly_stars": 0,
                    "monthly_stars": 0,
                    "daily_rank": 0,
                    "weekly_rank": 0,
                    "monthly_rank": 0,
                }
            raw_by_url[url][f"{since}_rank"] = rank
            dim_urls[since].append(url)

    # RSS 已按名次排序, 直接保序; 前端按 *_rank 升序展示
    dim_map = {dim: [raw_by_url[u] for u in urls] for dim, urls in dim_urls.items()}

    # total 维度改走 Search API, 真正"全站 Claude 相关按总 star 排", 不受 trending 池限制
    total_search_params = {
        "queries": params.get("total_queries") or [
            "claude in:name,description,readme",
            "topic:mcp",
        ],
        "per_query_limit": int(params.get("total_per_query_limit", 30)),
        "min_stars": int(params.get("total_min_stars", 30)),
    }
    try:
        search_pool = fetch_github_search(total_search_params)
    except Exception as e:
        errors.append(f"total: {type(e).__name__}: {e}")
        search_pool = []
    search_pool.sort(key=lambda x: x.get("total_stars_int", 0), reverse=True)
    dim_map["total"] = search_pool
    # total 单维度空但日周月正常时不会触发下面的全空 raise, 会被静默. 显式告警到 routine 日志,
    # 便于区分"GitHub 挡了机房 IP (需 GITHUB_TOKEN)"与"确实没结果".
    if not search_pool:
        why = errors[-1] if errors and errors[-1].startswith("total") else "search 返回空"
        print(f"[ai-news] github total 维度为空: {why} (未配 GITHUB_TOKEN 时机房 IP 易被限流/403)",
              file=sys.stderr)

    flat = []
    for dim in ("daily", "weekly", "monthly", "total"):
        for it in dim_map[dim]:
            flat.append({**it, "dimension": dim})

    # 四维度全空 = 真失败 (这两个源正常时恒有数据), 抛出让 fetch_one 记入 source.error,
    # 避免全站被封/限流 (含"HTTP 200 但空结果"这类不抛异常的失败) 仍假装成功只显示暂无数据.
    # 任一维度有数据即成功降级 (如 RSSHub 挂但 total 正常), 不误报.
    if not flat:
        detail = " | ".join(errors) if errors else "所有维度返回空 (无异常)"
        raise RuntimeError("github trending 无任何条目: " + detail)
    return flat


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


def _parse_atom(xml_bytes: bytes, max_items: int = 50) -> list:
    """解析 Atom 1.0 feed. 返回 [{title,url,desc,ts,author}].
    author 可能是作者名或空串.
    """
    import xml.etree.ElementTree as ET
    NS = "{http://www.w3.org/2005/Atom}"
    root = ET.fromstring(xml_bytes)
    out = []
    for entry in root.findall(f"{NS}entry"):
        title = (entry.findtext(f"{NS}title") or "").strip()
        if not title:
            continue
        # link: 取 rel="alternate" (或第一个 link)
        link = ""
        for l in entry.findall(f"{NS}link"):
            rel = l.get("rel", "alternate")
            if rel == "alternate" and l.get("href"):
                link = l.get("href", "").strip()
                break
        if not link:
            for l in entry.findall(f"{NS}link"):
                if l.get("href"):
                    link = l.get("href", "").strip()
                    break
        # summary 或 content 都作摘要, 清洗 HTML
        summary_raw = entry.findtext(f"{NS}summary") or entry.findtext(f"{NS}content") or ""
        desc = re.sub(r"<[^>]+>", "", summary_raw).strip()
        desc = re.sub(r"\s+", " ", desc)[:200]
        # published / updated
        ts = (entry.findtext(f"{NS}published") or entry.findtext(f"{NS}updated") or "").strip()
        # 归一化
        try:
            ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=timezone.utc)
            ts = ts_dt.astimezone(timezone.utc).isoformat(timespec="seconds")
        except Exception:
            pass
        # author
        author_el = entry.find(f"{NS}author/{NS}name")
        author = author_el.text.strip() if author_el is not None and author_el.text else ""
        out.append({
            "title": title, "url": link, "desc": desc, "ts": ts, "author": author,
        })
        if len(out) >= max_items:
            break
    return out


def fetch_atom(params: dict) -> list:
    """Atom feed 抓取. params:
    - url: Atom feed 地址
    - time_window_hours: 只保留窗口内条目 (按 published)
    - limit: 最多返回多少条
    """
    url = params["url"]
    window = int(params.get("time_window_hours", 48))
    limit = int(params.get("limit", 15))
    raw = _fetch(url)
    items = _parse_atom(raw, max_items=max(50, limit * 2))

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


# 默认参数：边界正文抓取 (#5) 优化值，对应 schemas.ARTICLE_TIMEOUT_SEC / ARTICLE_MAX_CHARS
# 不再硬编码 30s/6000 字 —— Phase 2 改成更快的 7s/3000 字（边界 cap 10-12 条并发跑）
ARTICLE_TIMEOUT = 7
ARTICLE_MAX_CHARS = 3000


def fetch_article_text(url: str, timeout: int = None, max_chars: int = None) -> tuple:
    """用 Jina Reader 抓文章正文. 返回 (text, err_str).
    text 去掉图片 md / 压缩空行, 截取到 max_chars.

    timeout / max_chars 可覆盖默认值，便于调参或测试。"""
    if not url or not url.startswith(("http://", "https://")):
        return "", "invalid url"
    t = timeout if timeout is not None else ARTICLE_TIMEOUT
    mc = max_chars if max_chars is not None else ARTICLE_MAX_CHARS
    jina_url = JINA_READER_PREFIX + url
    try:
        raw = _fetch(jina_url, timeout=t).decode("utf-8", errors="replace")
        raw = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw[:mc].strip(), ""
    except urllib.error.HTTPError as e:
        return "", f"jina http {e.code}"
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"


THREADS_GRAPHQL_URL = "https://www.threads.com/graphql/query"
THREADS_IG_APP_ID = "238260118697367"


def _load_threads_session(session_path: str) -> dict:
    # 优先 env var (云端 routine 不能放本地文件); fallback 本地文件 (mac fetch_debug)
    env_raw = os.environ.get("THREADS_SESSION_JSON", "").strip()
    if env_raw:
        return json.loads(env_raw)
    path = os.path.expanduser(session_path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _threads_post(endpoint: str, headers: dict, form: dict, timeout: int = TIMEOUT) -> dict:
    import urllib.parse as _up
    body = _up.urlencode(form).encode("utf-8")
    req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    # 响应首行就是 JSON (Meta 有时发 NDJSON, 取第一段够用)
    text = raw.decode("utf-8", errors="replace")
    return json.loads(text.split("\n", 1)[0])


def _walk_threads_posts(obj, seen: dict):
    """递归找 Threads post 节点. 判据: 同时含 code + caption + user.
    找到即 append 到 seen (以 pk 为 key 去重), 不再往下钻避免把引用/回复帖子也当顶层抓入.
    """
    if isinstance(obj, dict):
        if "code" in obj and "caption" in obj and "user" in obj:
            pk = obj.get("pk") or obj.get("id")
            if pk and pk not in seen:
                seen[pk] = obj
            return
        for v in obj.values():
            _walk_threads_posts(v, seen)
    elif isinstance(obj, list):
        for v in obj:
            _walk_threads_posts(v, seen)


def _find_next_cursor(obj):
    """递归找 page_info.end_cursor (has_next_page=True)."""
    if isinstance(obj, dict):
        pi = obj.get("page_info")
        if isinstance(pi, dict) and pi.get("has_next_page") and pi.get("end_cursor"):
            return pi.get("end_cursor")
        for v in obj.values():
            c = _find_next_cursor(v)
            if c:
                return c
    elif isinstance(obj, list):
        for v in obj:
            c = _find_next_cursor(v)
            if c:
                return c
    return None


def _has_chinese(text: str) -> bool:
    """判断字符串是否包含至少一个 CJK 汉字 (U+4E00..U+9FFF).
    注: 这个范围覆盖简中 + 繁中 + 日文汉字, 不覆盖日文假名和韩文谚文——
    所以纯日文假名 / 纯韩文 post 会被判为 no-CN, 和"过滤非中文 post"意图一致.
    """
    if not text:
        return False
    return any("一" <= c <= "鿿" for c in text)


def _build_feed_view_info(prev_posts: list, ai_pattern=None) -> str:
    """从上一页的 post 列表构造 feed_view_info JSON 字符串.

    AI 命中的 post 标 5-15 秒 dwell (正向兴趣信号), 其他 post 标 500-1800 毫秒 (快速划过).
    Meta 的 online learner 会把这解读为"用户在 AI 帖子停留、非 AI 快速跳过", 推更多 AI.

    schema 基于逆向工程社区常见形状; Meta 内部 schema 没公开, 不保证 100% 匹配.
    如果 Meta 拒绝, 等价于发空 [] (fallback 到原行为).
    """
    import random as _rnd
    entries = []
    for idx, p in enumerate(prev_posts):
        pk = p.get("pk") or p.get("id") or p.get("code")
        if not pk:
            continue
        caption = (p.get("caption") or {}).get("text", "") or ""
        is_ai = bool(ai_pattern and ai_pattern.search(caption))
        if is_ai:
            view_time = _rnd.randint(5000, 15000)
        else:
            view_time = _rnd.randint(500, 1800)
        entries.append({
            "media_id": str(pk),
            "view_time": view_time,
            "is_visible": True,
            "distance_from_top": idx,
        })
    return json.dumps(entries, separators=(",", ":"))


def _normalize_threads_post(p: dict) -> dict:
    user = p.get("user") or {}
    username = user.get("username", "") or ""
    caption = p.get("caption") or {}
    text = (caption.get("text") or "").strip()
    first_line = text.split("\n", 1)[0][:120] or f"@{username}"
    code = p.get("code", "") or ""
    taken_at = p.get("taken_at")
    try:
        ts = datetime.fromtimestamp(int(taken_at), tz=timezone.utc).isoformat(timespec="seconds")
    except Exception:
        ts = _now_iso()
    post_url = f"https://www.threads.com/@{username}/post/{code}" if username and code else ""
    tpai = p.get("text_post_app_info") or {}
    like_count = int(p.get("like_count", 0) or 0)
    reply_count = int(tpai.get("direct_reply_count", 0) or 0)
    return {
        "title": first_line,
        "url": post_url,
        "desc": text[:300],
        "ts": ts,
        "author": username,
        # 前端 payload schema 需要的兼容字段 (score ↔ like_count, comments ↔ reply_count)
        "score": like_count,
        "comments": reply_count,
        "hn_url": "",
        # threads 原生字段 (保留给未来扩展)
        "like_count": like_count,
        "reply_count": reply_count,
        "repost_count": int(tpai.get("repost_count", 0) or 0),
    }


def fetch_threads_home(params: dict) -> list:
    """用已登录 cookie 直调 Meta Relay GraphQL 抓 Threads 个人首页 feed.

    抓取策略: 多阶段 initial_load + pagination, 累计满/翻不动就 refresh.
    - 初始: `after=null, reason=initial_load` → 翻页累计 48h 内去重 post
    - Refresh 触发条件 (任一即触发):
        a) 48h 内累计数 >= `refresh_at` 的下一个倍数 (50 → refresh → 100 → refresh → ...)
        b) 翻页卡死 (response 里没 end_cursor / 下页全是 dup)
    - Refresh = 下一轮 `after=null, reason=initial_load`, 让 Meta 重推一批 top-of-feed
    - 终止: 累计 >= `limit` 或 refresh 次数 >= `max_refreshes` 或 page 次数 >= `pages`

    params:
    - session_file: 凭据 JSON 路径 (默认 ~/Desktop/ai-project/data/.threads-session.json)
    - limit: 最终目标累计数 (默认 100)
    - refresh_at: 每累计到这个倍数触发一次 refresh (默认 50)
    - max_refreshes: refresh 次数上限 (默认 10, 防止死循环; 一般用到 2-5 次就够)
    - pages: 所有阶段合计 HTTP 请求数硬上限 (默认 60)
    - time_window_hours: 只保留这个窗口内的 post (默认 48)
    - cursor_key: variables 里分页游标字段名 (默认 'after')
    - page_size_key / page_size: 分页大小字段名/值 (默认 'first'/25, 只在 variables 没提供时注入)

    凭据 JSON 结构 (浏览器 sniff 得到):
        {
          "cookie": "sessionid=...; csrftoken=...; ...",
          "headers": { "x-fb-lsd": "...", "x-fb-friendly-name": "...", ... },
          "body":    { "av": "...", "fb_dtsg": "...", "lsd": "...", "doc_id": "...", ... },
          "variables": { "first": 25, "after": null, ... }
        }
    fetcher 会把 variables 里的 cursor_key 换成当前游标, 其他字段原样 replay 浏览器发的请求.
    """
    session_path = params.get("session_file", "~/Desktop/ai-project/data/.threads-session.json")
    limit = int(params.get("limit", 100))
    refresh_at = int(params.get("refresh_at", 50))
    max_refreshes = int(params.get("max_refreshes", 10))
    pages = int(params.get("pages", 60))
    window = int(params.get("time_window_hours", 48))
    cursor_key = params.get("cursor_key", "after")
    page_size_key = params.get("page_size_key", "first")
    page_size = int(params.get("page_size", 25))
    require_chinese = bool(params.get("require_chinese", True))
    simulate_ai_dwell = bool(params.get("simulate_ai_dwell", True))
    # 页间 sleep 范围 (秒), 模拟真人阅读速度, 兼顾 Meta 反爬
    page_delay_min = float(params.get("page_delay_min", 4.0))
    page_delay_max = float(params.get("page_delay_max", 9.0))

    session = _load_threads_session(session_path)
    cookie = session.get("cookie") or ""
    sniff_headers = session.get("headers") or {}
    body_base = session.get("body") or {}
    variables_tpl = dict(session.get("variables") or {})
    endpoint = session.get("endpoint") or THREADS_GRAPHQL_URL
    if page_size_key not in variables_tpl:
        variables_tpl[page_size_key] = page_size

    headers = {
        "content-type": "application/x-www-form-urlencoded",
        "cookie": cookie,
        "x-ig-app-id": THREADS_IG_APP_ID,
        "accept": "*/*",
        "origin": "https://www.threads.com",
        "referer": "https://www.threads.com/",
        "user-agent": sniff_headers.get("user-agent") or UA,
    }
    for k, v in sniff_headers.items():
        if v is not None:
            headers[k.lower()] = v
    # cookie 如果 sniff_headers 里也有, session.cookie 优先 (明确字段)
    headers["cookie"] = cookie

    cutoff = datetime.now(timezone.utc) - timedelta(hours=window)

    def _in_window(post) -> bool:
        ta = post.get("taken_at")
        if not ta:
            return True  # 拿不到时间就保守放行, 最终正规化时会再过一遍窗口
        try:
            return datetime.fromtimestamp(int(ta), tz=timezone.utc) >= cutoff
        except Exception:
            return True

    def _count_in_window(seen_map):
        return sum(1 for p in seen_map.values() if _in_window(p))

    # 懒 import, 避免给模块顶部增加不必要依赖
    import random as _rnd
    import time as _time
    # 延迟 import filters 避免循环依赖 (filters.py 没 import fetchers, 所以安全)
    _ai_pat = None
    if simulate_ai_dwell:
        try:
            from ai_news.data.filters import THREADS_LOOSE_RE as _ai_pat
        except Exception:
            _ai_pat = None

    seen = {}
    cursor = None
    reason = "initial_load"
    refresh_count = 0
    just_refreshed = False  # 上一轮是否刚 refresh (用于检测 dry refresh)
    # 已经触发过 milestone refresh 的"累计值档位"集合, 防止反复触发同一档位
    milestones_hit = set()
    # 上一次 walker 抓到的 posts 列表 (用于构造下一次的 feed_view_info)
    prev_page_posts = []
    page_idx = 0
    for _ in range(max(1, pages)):
        variables_tpl[cursor_key] = cursor
        if isinstance(variables_tpl.get("data"), dict):
            variables_tpl["data"]["reason"] = reason
            # AI dwell simulation: 从第 2 页开始 (第 1 页是 initial_load 没有前一页可报)
            if simulate_ai_dwell and page_idx > 0 and prev_page_posts:
                variables_tpl["data"]["feed_view_info"] = _build_feed_view_info(prev_page_posts, _ai_pat)
            else:
                variables_tpl["data"].setdefault("feed_view_info", "[]")
        # 页间 sleep: 模拟真人阅读速度
        if page_idx > 0 and page_delay_max > 0:
            _time.sleep(_rnd.uniform(page_delay_min, page_delay_max))
        page_idx += 1

        form = dict(body_base)
        form["variables"] = json.dumps(variables_tpl, ensure_ascii=False)
        try:
            resp = _threads_post(endpoint, headers, form)
        except Exception:
            break
        if not isinstance(resp, dict) or resp.get("errors"):
            break
        before = len(seen)
        # 记录这一页新增的 post (用于下一轮 feed_view_info)
        page_snapshot = {}
        _walk_threads_posts(resp, page_snapshot)
        prev_page_posts = list(page_snapshot.values())
        # 合并到全量 seen
        for pk, p in page_snapshot.items():
            if pk not in seen:
                seen[pk] = p
        got_new = len(seen) > before
        in_window_count = _count_in_window(seen)

        # Refresh 完的第一页就没新 post = Meta 已经没 fresh 内容可给, 早停
        if just_refreshed and not got_new:
            break
        just_refreshed = False

        if in_window_count >= limit:
            break

        next_cursor = _find_next_cursor(resp)
        stuck = (not got_new) or (not next_cursor) or (next_cursor == cursor)
        # milestone: 当前累计值所处的 refresh_at 档位 (50→1, 100→2, ...)
        tier = in_window_count // refresh_at if refresh_at > 0 else 0
        need_milestone_refresh = (tier >= 1 and tier not in milestones_hit
                                   and in_window_count < limit)

        if stuck or need_milestone_refresh:
            # Refresh 只允许发生在已经攒到 refresh_at 之后
            # (在这之前翻不动就直接结束, 不拿 refresh 当兜底)
            if in_window_count < refresh_at:
                break
            if refresh_count >= max_refreshes:
                break
            if need_milestone_refresh:
                milestones_hit.add(tier)
            cursor = None
            reason = "initial_load"
            refresh_count += 1
            just_refreshed = True
            continue

        cursor = next_cursor
        reason = "pagination"

    items = []
    for p in seen.values():
        it = _normalize_threads_post(p)
        # 非中文 post 过滤 (title + desc 都不含汉字就剔)
        if require_chinese and not _has_chinese(it.get("title", "") + " " + it.get("desc", "")):
            continue
        try:
            ts_dt = datetime.fromisoformat(it["ts"].replace("Z", "+00:00"))
            if ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=timezone.utc)
            if ts_dt >= cutoff:
                items.append(it)
        except Exception:
            items.append(it)
    items.sort(key=lambda x: (x.get("like_count", 0), x.get("reply_count", 0)), reverse=True)
    return items[:limit]


_TS_LABEL_RE = re.compile(r"^(\d+)\s*(小時|分鐘|天|週|月|年|hour|hours|minute|minutes|day|days|week|month|year)s?$")
_DATE_LABEL_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")


def _parse_threads_timestamp_label(label, snapshot_ts):
    """'9小時' / '1天' / '2026-3-13' -> ISO datetime, 失败返回 None."""
    if not label:
        return None
    if _DATE_LABEL_RE.match(label):
        try:
            d = datetime.strptime(label, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return d.isoformat(timespec="seconds")
        except Exception:
            return None
    m = _TS_LABEL_RE.match(label)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)
    try:
        base = datetime.fromisoformat(snapshot_ts.replace("Z", "+00:00"))
    except Exception:
        base = datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    if unit in ("小時", "hour", "hours"):
        return (base - timedelta(hours=n)).isoformat(timespec="seconds")
    if unit in ("分鐘", "minute", "minutes"):
        return (base - timedelta(minutes=n)).isoformat(timespec="seconds")
    if unit in ("天", "day", "days"):
        return (base - timedelta(days=n)).isoformat(timespec="seconds")
    if unit in ("週", "week"):
        return (base - timedelta(weeks=n)).isoformat(timespec="seconds")
    if unit in ("月",):
        return (base - timedelta(days=n * 30)).isoformat(timespec="seconds")
    if unit in ("年",):
        return (base - timedelta(days=n * 365)).isoformat(timespec="seconds")
    return None


def _clean_threads_body(body: str, timestamp_label: str, username: str) -> str:
    """去掉 body 开头的时间戳标签和尾部的 '翻譯' 等噪声."""
    if not body:
        return ""
    txt = body.strip()
    # 去头部重复的时间戳 (DOM 拼接时可能把时间戳插到正文开头)
    if timestamp_label and txt.startswith(timestamp_label):
        txt = txt[len(timestamp_label):].strip()
    # 去头部重复的 username (有时 DOM 把 username 也拼进 body)
    for prefix in (username, f"@{username}"):
        if prefix and txt.startswith(prefix):
            txt = txt[len(prefix):].strip()
    # 去尾部 "翻譯" / "Translate"
    txt = re.sub(r"\s*(翻譯|Translate)\s*$", "", txt)
    return txt.strip()


def fetch_threads_snapshot(params: dict) -> list:
    """读取浏览器一次性导出的 Threads For You 快照 (由 Playwright MCP 采集).

    快照 JSON schema (ai-project/data/threads-snapshot.json):
        { "ts": ISO8601,  "source": "threads_for_you_dom_scrape",
          "count": int,   "posts": [
            {"username", "code", "url", "datetime" | null,
             "timestamp_label", "title", "body", "engagement_nums": [...]}
          ] }

    params:
    - snapshot_file: 快照路径 (默认 ~/Desktop/ai-project/data/threads-snapshot.json)
    - time_window_hours: 只保留窗口内 post (默认 48)
    - limit: 最多返回 (默认 200)
    - min_body_len: 过滤 body 太短的 post (默认 10 字符, 防止只有 emoji)
    """
    path = os.path.expanduser(params.get("snapshot_file", "~/Desktop/ai-project/data/threads-snapshot.json"))
    window = int(params.get("time_window_hours", 48))
    limit = int(params.get("limit", 200))
    min_body = int(params.get("min_body_len", 10))
    require_chinese = bool(params.get("require_chinese", True))
    with open(path, "r", encoding="utf-8") as f:
        snap = json.load(f)
    snapshot_ts = snap.get("ts") or _now_iso()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window)

    items = []
    for p in snap.get("posts", []):
        username = (p.get("username") or "").strip()
        code = (p.get("code") or "").strip()
        if not username or not code:
            continue
        ts_iso = p.get("datetime") or _parse_threads_timestamp_label(p.get("timestamp_label"), snapshot_ts) or snapshot_ts
        # 时窗过滤 (保守: 解析失败保留)
        try:
            ts_dt = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
            if ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=timezone.utc)
            if ts_dt < cutoff:
                continue
        except Exception:
            pass
        body = _clean_threads_body(p.get("body", ""), p.get("timestamp_label", ""), username)
        if len(body) < min_body:
            continue
        if require_chinese and not _has_chinese(body):
            continue
        first_line = body.split("\n", 1)[0]
        # title 换成 body 首句 (避免之前 '9小時' 这种脏数据)
        title = first_line[:120].strip() or f"@{username}"
        eng = p.get("engagement_nums") or []
        # 经验: Threads 数字行 = [views(有时), likes, replies, reposts], 末尾三个常见
        like_count = int(eng[0]) if eng else 0
        items.append({
            "title": title,
            "url": p.get("url") or f"https://www.threads.com/@{username}/post/{code}",
            "desc": body[:300],
            "ts": ts_iso,
            "author": username,
            "like_count": like_count,
            "engagement": eng,
        })
    items.sort(key=lambda x: x.get("like_count", 0), reverse=True)
    return items[:limit]


_TYPE_DISPATCH = {
    "hn_algolia": fetch_hn_algolia,
    "github_trending": fetch_github_trending,
    "github_trending_multi": fetch_github_trending_multi,
    "rss": fetch_rss,
    "atom": fetch_atom,
    "threads_home": fetch_threads_home,
    "threads_snapshot": fetch_threads_snapshot,
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
