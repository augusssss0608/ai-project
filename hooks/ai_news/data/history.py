"""历史持久化 (负例数据源). append-only jsonl, 查询时按 url 聚合."""
import json
import os
from datetime import datetime, timedelta, timezone

# repo-relative: 兼容 mac (~/Desktop/ai-project) 和云端 routine (/home/user/ai-project)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
HISTORY_PATH = os.path.join(_REPO_ROOT, "cloud-sync", "ai-news-history.jsonl")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def append_items(items: list):
    """每次 pipeline 跑完, append 所有展示过的 items.
    item 至少含 source / url / title / desc.
    允许同 url 重复行 (查询时聚合)."""
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    ts = _now_iso()
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        for it in items:
            row = {
                "ts": ts,
                "source": it.get("source", ""),
                "url": it.get("url", ""),
                "title": it.get("title", ""),
                "desc": it.get("desc", "")[:200],
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _iter_history():
    if not os.path.isfile(HISTORY_PATH):
        return
    with open(HISTORY_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def load_all_urls() -> set:
    """返回 history.jsonl 里出现过的所有 URL 集合 (跨源). 用于全量去重."""
    urls = set()
    for row in _iter_history():
        url = row.get("url", "")
        if url:
            urls.add(url)
    return urls


def aggregate_by_url(source_id: str) -> list:
    """读 jsonl, 按 url 聚合 (first_ts=min, last_ts=max, count). 返回列表."""
    agg = {}
    for row in _iter_history():
        if row.get("source") != source_id:
            continue
        url = row.get("url", "")
        if not url:
            continue
        ts = row.get("ts", "")
        if url not in agg:
            agg[url] = {
                "url": url,
                "title": row.get("title", ""),
                "desc": row.get("desc", ""),
                "first_ts": ts,
                "last_ts": ts,
                "count": 1,
            }
        else:
            a = agg[url]
            a["count"] += 1
            if ts < a["first_ts"]:
                a["first_ts"] = ts
            if ts > a["last_ts"]:
                a["last_ts"] = ts
    return list(agg.values())


def get_negatives(source_id: str, feedback: dict, days: int = 7, limit: int = 30) -> list:
    """该源条目中 url 不在 feedback.votes 且 first_ts <= now - days, 按 count desc 取 limit."""
    voted_urls = set(feedback.get("votes", {}).keys())
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    agg = aggregate_by_url(source_id)
    out = []
    for a in agg:
        if a["url"] in voted_urls:
            continue
        try:
            ft = datetime.fromisoformat(a["first_ts"].replace("Z", "+00:00"))
            if ft.tzinfo is None:
                ft = ft.replace(tzinfo=timezone.utc)
            if ft > cutoff:
                continue
        except Exception:
            continue
        out.append(a)
    out.sort(key=lambda x: x["count"], reverse=True)
    return out[:limit]
