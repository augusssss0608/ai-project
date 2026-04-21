#!/usr/bin/env python3
"""AI news fetcher — stdlib-only.

从多个公开源抓取 AI/Claude 相关新闻与开源项目, 聚合成 JSON 供 dashboard 消费.

输出: ~/Desktop/ai-project/data/ai-news.json

可手动运行, 也可挂 cron:
    0 8 * * * /usr/bin/env python3 ~/Desktop/ai-project/hooks/fetch-ai-news.py
"""
import json
import os
import re
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from html.parser import HTMLParser

OUT_PATH = os.path.expanduser("~/Desktop/ai-project/data/ai-news.json")
TIMEOUT = 12
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) claude-code-dashboard/1.0"

# ===== 摘要 / 分析生成 (Jina Reader + claude CLI) =====
import subprocess
JINA_READER_PREFIX = "https://r.jina.ai/"
ARTICLE_TIMEOUT = 30
ARTICLE_MAX_CHARS = 6000  # 传给 LLM 的正文上限
HAIKU_MODEL = os.environ.get("AI_NEWS_HAIKU_MODEL", "claude-haiku-4-5")
OPUS_MODEL = os.environ.get("AI_NEWS_OPUS_MODEL", "claude-opus-4-7")
CLAUDE_CLI = os.environ.get("CLAUDE_CLI", "claude")
CLAUDE_TIMEOUT = 90
# 并发度: Jina 抓正文 I/O 密集用 6, claude -p CPU/子进程密集用 3
JINA_WORKERS = 6
SUMMARY_WORKERS = 3

# HN Algolia query — AI / Claude / LLM / MCP 关键词过滤, 昨日至今
HN_QUERY = "AI OR Claude OR Anthropic OR LLM OR MCP OR OpenAI OR Gemini OR DeepSeek"
HN_LIMIT = 15
GITHUB_TRENDING_URL = "https://github.com/trending?since=daily"
QBITAI_RSS_URL = "https://www.qbitai.com/feed"
ITHOME_RSS_URL = "https://www.ithome.com.tw/rss"

# 核心 AI 产品名: 命中即视为强信号, 只被 HARD_NOISE 否决
CORE_AI_RE = re.compile(
    r"(Claude|Anthropic|ChatGPT|OpenAI|GPT-|Sora|Gemini|Bard|DeepSeek|Qwen|"
    r"LLaMA|Llama|Mistral|Grok|Copilot|Cursor|Perplexity|Midjourney|Firefly|"
    r"Stable\s*Diffusion|Hugging\s*Face|Kimi|Doubao|豆包|文心|通義|通义|"
    r"智譜|智谱|GLM|Minimax|百川|"
    r"Opus|Sonnet|Haiku)",
    re.I)

# 次级 AI 关键词: 命中 + 无 soft NOISE 才 keep
AI_PRODUCT_RE = re.compile(
    r"(" + CORE_AI_RE.pattern.strip("()") + r"|"
    r"o1\b|o3\b|o4\b|o5\b|Yi\b|MCP|agent|agentic|"
    r"大(?:型|语|語)言模型|大模型|生成式|人工智慧|人工智能|LLM)", re.I)

# 业务/产业/资安/时事噪音: 命中则剔除
_NOISE_TERMS = [
    # 商业/财报
    "融資", "融资", "併購", "并购", "IPO", "收購", "收购", "股價", "股价",
    "估值", "投資人", "投资人", "私募", "募資", "募资", "季報", "季报",
    "財報", "财报", "營收", "营收", "業績", "业绩", "淨利", "净利",
    # 产业/供应链/硬件
    "工廠", "工厂", "產業鏈", "产业链", "供應鏈", "供应链", "晶圓", "晶圆",
    "代工", "製造業", "制造业", "產業界", "产业界",
    # 车相关
    "汽車", "汽车", "電動車", "电动车", "自動駕駛", "自动驾驶", "造車", "造车",
    "車企", "车企", "NOA", "自駕", "自驾", "智駕", "智驾", "充電樁", "充电桩",
    # ESG/永续
    "ESG", "淨零", "净零", "永續", "永续", "減碳", "减碳", "碳排",
    # 资安/漏洞/攻击
    "資安", "资安", "漏洞", "駭客", "骇客", "攻擊", "攻击", "惡意", "恶意",
    "malware", "ransomware", "CVE", "NKAbuse", "詐騙", "诈骗", "釣魚", "钓鱼",
    # 认证/合规/政策
    "FIDO", "KYA", "KYC", "GDPR", "合規", "合规", "審計", "审计",
    "制裁", "禁令", "關稅", "关税", "貿易戰", "贸易战", "出口管制",
    # 医疗/人文
    "醫療", "医疗", "診斷", "诊断", "臨床", "临床",
    # 其他噪音
    "週報", "周报", "回顧", "回顾",
]
NOISE_RE = re.compile("|".join(re.escape(t) for t in _NOISE_TERMS), re.I)

# 硬 NOISE: 即使含 CORE AI 产品名也要剔除 (新闻主题是漏洞/攻击/融资而非产品进展)
_HARD_NOISE_TERMS = [
    "漏洞", "駭客", "骇客", "攻擊", "攻击", "惡意", "恶意", "malware",
    "ransomware", "詐騙", "诈骗", "CVE", "NKAbuse", "零時差", "零日",
    "併購", "并购", "融資", "融资", "IPO", "收購", "收购", "股價", "股价",
    "關稅", "关税", "制裁",
]
HARD_NOISE_RE = re.compile("|".join(re.escape(t) for t in _HARD_NOISE_TERMS), re.I)


def _is_pure_ai_news(title: str, desc: str = "") -> bool:
    """双层过滤:
    1) 命中 HARD_NOISE → 直接剔除 (漏洞/攻击/融资)
    2) 命中 CORE AI 产品名 (Claude/GPT/Gemini/...) → keep (忽略 soft noise)
    3) 命中次级 AI 关键词 (agent/LLM/生成式) → 再检查 soft noise 才 keep
    """
    if HARD_NOISE_RE.search(title):
        return False
    if CORE_AI_RE.search(title):
        return True
    if AI_PRODUCT_RE.search(title) and not NOISE_RE.search(title):
        return True
    return False


def _fetch(url: str, headers=None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


HN_KEYWORDS = re.compile(
    r"\b(ai|agent|agentic|llm|gpt|claude|anthropic|openai|gemini|deepseek|"
    r"mistral|llama|mcp|rag|transformer|diffusion|stable\s*diffusion|"
    r"hugging\s*face|langchain|cursor|copilot|nerf|embedding)\b", re.I)


def fetch_hackernews() -> dict:
    """HN Algolia: 抓 front_page + search_by_date 最近 48h 高分帖, 客户端按关键词过滤."""
    try:
        all_hits = {}
        # 1) front_page: 当前首页
        url1 = "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=50"
        for h in json.loads(_fetch(url1)).get("hits", []):
            all_hits[h.get("objectID")] = h
        # 2) 最近 48h 按分数降序的 story
        since = int(datetime.now(timezone.utc).timestamp()) - 86400 * 2
        url2 = f"https://hn.algolia.com/api/v1/search?tags=story&numericFilters=points%3E30,created_at_i%3E{since}&hitsPerPage=50"
        for h in json.loads(_fetch(url2)).get("hits", []):
            all_hits[h.get("objectID")] = h
        # 过滤关键词命中 + 去重
        items = []
        for h in all_hits.values():
            title = (h.get("title") or h.get("story_title") or "").strip()
            if not title or not HN_KEYWORDS.search(title):
                continue
            items.append({
                "title": title,
                "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                "hn_url": f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                "score": h.get("points", 0),
                "comments": h.get("num_comments", 0),
                "ts": h.get("created_at", ""),
                "author": h.get("author", ""),
            })
        items.sort(key=lambda x: x["score"] or 0, reverse=True)
        return {
            "id": "hackernews",
            "label": "Hacker News",
            "source_url": "https://news.ycombinator.com/",
            "updated_at": _now_iso(),
            "items": items[:HN_LIMIT],
            "error": None,
        }
    except Exception as e:
        return {"id": "hackernews", "label": "Hacker News", "updated_at": _now_iso(),
                "items": [], "error": str(e), "source_url": "https://news.ycombinator.com/"}


class _TrendingParser(HTMLParser):
    """解析 github.com/trending 页面 HTML.

    结构简化: 每个 repo 是 <article class='Box-row'>, 内含:
      - <h2><a href='/owner/repo'>...</a></h2>  仓库名
      - <p class='col-9 ...'>描述</p>            可选描述
      - <a class='Link--muted' href='.../stargazers'>{total_stars}</a>
      - <span class='d-inline-block float-sm-right'>{today_stars} stars today</span>
      - <span itemprop='programmingLanguage'>Python</span>  可选
    """
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
            self._cur = {"title": "", "url": "", "desc": "", "lang": "", "stars": "", "today_stars": ""}
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
            self._cur["today_stars"] = "".join(self._buf).strip()
            self._capture = None; self._buf = []
        elif tag == "article" and self._in_article:
            if self._cur and self._cur["title"]:
                self.items.append(self._cur)
            self._in_article = False
            self._cur = None
            self._capture = None
            self._buf = []


def fetch_github_trending() -> dict:
    try:
        raw = _fetch(GITHUB_TRENDING_URL).decode("utf-8", errors="ignore")
        p = _TrendingParser()
        p.feed(raw)
        items = []
        for it in p.items[:20]:
            items.append({
                "title": it["title"],
                "url": it["url"],
                "desc": it["desc"][:200],
                "lang": it["lang"],
                "stars": it["stars"],
                "today_stars": it["today_stars"],
            })
        return {
            "id": "github_trending",
            "label": "GitHub Trending (daily)",
            "source_url": GITHUB_TRENDING_URL,
            "updated_at": _now_iso(),
            "items": items,
            "error": None,
        }
    except Exception as e:
        return {"id": "github_trending", "label": "GitHub Trending (daily)",
                "updated_at": _now_iso(), "items": [], "error": str(e),
                "source_url": GITHUB_TRENDING_URL}


def fetch_qbitai() -> dict:
    """量子位 RSS — 用纯 AI 产品新闻过滤 (剔除智能车/产业/融资)."""
    try:
        def _filt(title, item_el):
            return _is_pure_ai_news(title)
        raw = _fetch(QBITAI_RSS_URL)
        items = _parse_rss2(raw, title_filter=_filt, max_items=15)
        return {
            "id": "qbitai",
            "label": "量子位",
            "source_url": "https://www.qbitai.com/",
            "updated_at": _now_iso(),
            "items": items,
            "error": None,
        }
    except Exception as e:
        return {"id": "qbitai", "label": "量子位", "updated_at": _now_iso(),
                "items": [], "error": str(e), "source_url": "https://www.qbitai.com/"}


def _parse_rss2(xml_bytes: bytes, title_filter=None, max_items: int = 15) -> list:
    """通用 RSS 2.0 <channel><item> 解析器. 返回 [{title,url,desc,ts,author}]."""
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
        if title_filter is not None and not title_filter(title, it):
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


def fetch_ithome() -> dict:
    """iThome 台湾 IT 媒体 RSS, 纯 AI 产品新闻过滤 (剔除资安/ESG/产业)."""
    try:
        def _filt(title, item_el):
            return _is_pure_ai_news(title)
        raw = _fetch(ITHOME_RSS_URL)
        items = _parse_rss2(raw, title_filter=_filt, max_items=15)
        return {
            "id": "ithome_tw",
            "label": "iThome (台湾)",
            "source_url": "https://www.ithome.com.tw/",
            "updated_at": _now_iso(),
            "items": items,
            "error": None,
        }
    except Exception as e:
        return {"id": "ithome_tw", "label": "iThome (台湾)", "updated_at": _now_iso(),
                "items": [], "error": str(e), "source_url": "https://www.ithome.com.tw/"}


# ============================================================
# 文章正文抓取 (Jina Reader)
# ============================================================
def fetch_article_text(url: str) -> tuple:
    """用 Jina Reader 抓取文章正文 markdown. 返回 (text, err)."""
    if not url or not url.startswith(("http://", "https://")):
        return "", "invalid url"
    jina_url = JINA_READER_PREFIX + url
    try:
        req = urllib.request.Request(jina_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=ARTICLE_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        # 去掉 Jina 输出的图片 markdown 行, 节省 LLM context
        raw = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", raw)
        # 压缩多个空行
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw[:ARTICLE_MAX_CHARS].strip(), ""
    except urllib.error.HTTPError as e:
        return "", f"jina http {e.code}"
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"


# ============================================================
# claude -p 子进程调用
# ============================================================
def _call_claude(prompt: str, model: str) -> tuple:
    try:
        env = os.environ.copy()
        env["CLAUDE_SKIP_SESSION_START"] = "1"
        result = subprocess.run(
            [CLAUDE_CLI, "-p", prompt, "--model", model],
            capture_output=True, text=True,
            timeout=CLAUDE_TIMEOUT, env=env,
        )
    except FileNotFoundError:
        return "", f"{CLAUDE_CLI} CLI 未找到"
    except subprocess.TimeoutExpired:
        return "", f"claude 超时 ({CLAUDE_TIMEOUT}s)"
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()[:160]
        return "", f"退出码 {result.returncode}: {err}"
    return (result.stdout or "").strip(), ""


def haiku_summary(title: str, article_text: str) -> tuple:
    """haiku 生成 50-80 字中文重点摘要."""
    content = article_text or "(无法抓取正文, 仅凭标题)"
    prompt = (
        "你是科技新闻编辑。用简洁中文概括下面这篇 AI/科技文章的核心要点, "
        "50-80 字, 只写结论不要铺垫, 不要 markdown/引号/前后缀.\n\n"
        f"标题: {title}\n\n正文:\n{content}"
    )
    text, err = _call_claude(prompt, HAIKU_MODEL)
    if err:
        return "", err
    # 清理引号/代码块
    for ch in ['"', "'", "「", "」", "```", "`"]:
        text = text.replace(ch, "")
    return text.strip()[:200], ""


def opus_analysis(title: str, article_text: str) -> dict:
    """opus 分析两个维度: 工作区帮助 + Claude 使用. 无相关输出'无相关'."""
    content = article_text or "(无法抓取正文, 仅凭标题)"
    prompt = (
        "分析下面这篇 AI/科技文章与以下两个方向的相关性:\n"
        "方向1 — 对当前工作区的帮助: 工作区是 Flutter 直播 App + Go (Kratos) 后端 + Lua 遗留服务 + 管理后台的多端项目\n"
        "方向2 — 优化 Claude Code 使用: 新 skill/plugin/prompt 技巧/模型能力变化/工作流改进\n\n"
        "每个方向一句中文 (30-60字)。如该方向无关, 直接写 '无相关'。\n"
        "严格按两行格式输出, 不要其他文字:\n"
        "工作区帮助: <一句话 或 无相关>\n"
        "Claude使用: <一句话 或 无相关>\n\n"
        f"文章标题: {title}\n\n文章正文:\n{content}"
    )
    text, err = _call_claude(prompt, OPUS_MODEL)
    result = {"workspace_help": "", "claude_usage": "", "error": err}
    if err:
        return result
    # 解析两行
    for line in text.split("\n"):
        line = line.strip().lstrip("-*").strip()
        if not line:
            continue
        # 兼容 繁/简 冒号 全/半角
        for key_zh, out_field in (("工作区帮助", "workspace_help"),
                                  ("工作區幫助", "workspace_help"),
                                  ("Claude使用", "claude_usage"),
                                  ("Claude 使用", "claude_usage")):
            if line.startswith(key_zh):
                rest = line[len(key_zh):].lstrip(":：").strip()
                result[out_field] = rest[:200]
                break
    # 如果解析失败 (LLM 没按格式), 把全文塞进 workspace_help 做兜底
    if not result["workspace_help"] and not result["claude_usage"]:
        result["workspace_help"] = text[:200]
    return result


# ============================================================
# 整合: 对一篇文章走完整流程
# ============================================================
def _summarize_one(item: dict) -> dict:
    """item in-place 加字段 summary / workspace_help / claude_usage / summary_error."""
    title = item.get("title", "").strip()
    url = item.get("url", "")
    if not title:
        return item
    article, art_err = ("", "")
    if url and url.startswith("http"):
        article, art_err = fetch_article_text(url)
    # haiku 摘要
    summary, h_err = haiku_summary(title, article)
    item["summary"] = summary
    # opus 分析
    opus = opus_analysis(title, article)
    item["workspace_help"] = opus["workspace_help"] or "无相关"
    item["claude_usage"] = opus["claude_usage"] or "无相关"
    errs = [e for e in (art_err, h_err, opus["error"]) if e]
    item["summary_error"] = "; ".join(errs) if errs else ""
    return item


def enrich_sources_with_summaries(sources: list):
    """对所有源的所有 item 生成摘要 + 分析. 就地修改 item."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    all_items = [it for s in sources for it in s.get("items", [])]
    total = len(all_items)
    if total == 0:
        return
    print(f"[ai-news] 开始对 {total} 条文章生成 haiku 摘要 + opus 分析...", file=sys.stderr)
    done = 0
    with ThreadPoolExecutor(max_workers=SUMMARY_WORKERS) as pool:
        futures = {pool.submit(_summarize_one, it): it for it in all_items}
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as e:
                it = futures[fut]
                it["summary_error"] = f"pipeline: {e}"
            done += 1
            if done % 5 == 0 or done == total:
                print(f"[ai-news] summarize {done}/{total}", file=sys.stderr)


def main():
    # --no-summary 跳过摘要生成 (手动测试抓取时用)
    skip_summary = "--no-summary" in sys.argv
    sources = []
    sources.append(fetch_hackernews())
    sources.append(fetch_github_trending())
    sources.append(fetch_qbitai())
    sources.append(fetch_ithome())

    # 对所有条目生成 haiku 摘要 + opus 双维度分析 (就地修改 item)
    if not skip_summary:
        try:
            enrich_sources_with_summaries(sources)
        except Exception as e:
            print(f"[ai-news] summarization failed: {e}", file=sys.stderr)

    payload = {
        "updated_at": _now_iso(),
        "sources": sources,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, OUT_PATH)

    total = sum(len(s["items"]) for s in sources)
    errs = [s["label"] for s in sources if s.get("error")]
    print(f"[ai-news] {total} items written to {OUT_PATH}")
    if errs:
        print(f"[ai-news] sources with errors: {', '.join(errs)}", file=sys.stderr)
    return 0 if total > 0 else 2


if __name__ == "__main__":
    sys.exit(main())
