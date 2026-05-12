"""#5 边界正文抓取：选边界候选 + ThreadPool 并发抓 Jina 正文。

调用顺序（pipeline §2.4b）：
1. select_boundary_candidates(scored_pool) → 选 cap 10 条边界
2. fetch_boundary_contents(items) → 并发抓正文，附 full_content + content_status
3. 抓取结果按源分组传给二轮 scorer
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import schemas
from .fetchers import fetch_article_text


def select_boundary_candidates(
    scored_pool: list,
    cap: int = schemas.DEFAULT_BOUNDARY_CAP,
    hard_cap: int = schemas.HARD_BOUNDARY_CAP,
    min_fetch: int = schemas.MIN_BOUNDARY_FETCH,
) -> list:
    """从全局 scored pool 选 #5 边界候选。

    规则：
    1. 排除 EXCLUDED_FROM_MMR 中的源（github_trending）
    2. 取 title_score in [LOW, HIGH] 的候选
    3. 数量 <= cap：全选
    4. 数量 > cap：按 title_score desc 取前 cap
    5. 数量 < min_fetch：从 rank 6-15 补足到 min_fetch（仅非 excluded 源）
    6. 最终硬上限 hard_cap

    scored_pool 中每项要求字段：source, title_score。
    """
    if not scored_pool:
        return []

    # 过滤掉不参与 MMR 的源
    eligible = [
        it for it in scored_pool
        if it.get("source") not in schemas.EXCLUDED_FROM_MMR
        and isinstance(it.get("title_score"), (int, float))
    ]
    if not eligible:
        return []

    # 边界范围
    lo = schemas.TITLE_SCORE_BOUNDARY_LOW
    hi = schemas.TITLE_SCORE_BOUNDARY_HIGH
    boundary = [it for it in eligible if lo <= it["title_score"] <= hi]

    # 按 title_score desc 排序，便于截取或补足时的优先级
    boundary.sort(key=lambda x: x["title_score"], reverse=True)

    if len(boundary) > cap:
        selected = boundary[:cap]
    elif len(boundary) >= min_fetch:
        selected = boundary
    else:
        # 边界候选不足 min_fetch，从全局非边界 rank 6-15 补足
        # 全局 rank：按 title_score desc 全 eligible 排序
        ranked = sorted(eligible, key=lambda x: x["title_score"], reverse=True)
        # 排除已选边界
        boundary_urls = {it.get("url") for it in boundary}
        # rank 6-15（0-indexed 5..14）
        fillers = [
            it for it in ranked[5:15]
            if it.get("url") not in boundary_urls
        ]
        needed = min_fetch - len(boundary)
        selected = boundary + fillers[:needed]

    # 硬上限
    return selected[:hard_cap]


def fetch_boundary_contents(
    items: list,
    max_workers: int = schemas.FETCH_MAX_WORKERS,
    timeout: int = schemas.ARTICLE_TIMEOUT_SEC,
    max_chars: int = schemas.ARTICLE_MAX_CHARS,
) -> dict:
    """并发抓边界候选的正文。

    在原 items 上原地 append 字段：
      - full_content: str（成功）或 ""（失败）
      - content_status: "fetched" / "failed"
      - fetch_latency_sec: float（实际耗时，便于 metrics）
      - fetch_error: str（仅失败时记录）

    返回 metrics dict 供 pipeline_metrics.boundary_fetch 用：
      {attempted, succeeded, failed, success_rate, avg_latency_sec, latencies}
    """
    if not items:
        return {
            "attempted": 0, "succeeded": 0, "failed": 0,
            "success_rate": 0.0, "avg_latency_sec": 0.0,
            "latencies": [],
        }

    def _worker(idx_item):
        idx, item = idx_item
        url = item.get("url", "")
        t0 = time.monotonic()
        text, err = fetch_article_text(url, timeout=timeout, max_chars=max_chars)
        elapsed = time.monotonic() - t0
        return idx, text, err, elapsed

    succeeded = 0
    failed = 0
    latencies = []

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_worker, (i, it)) for i, it in enumerate(items)]
        for fut in as_completed(futures):
            try:
                idx, text, err, elapsed = fut.result()
            except Exception as e:
                # _worker 自己已经 swallow 大部分错误，这里只兜底
                idx, text, err, elapsed = -1, "", f"future_exception: {e}", 0.0
            latencies.append(elapsed)
            if idx < 0:
                failed += 1
                continue
            item = items[idx]
            item["fetch_latency_sec"] = round(elapsed, 2)
            if text:
                item["full_content"] = text
                item["content_status"] = schemas.CONTENT_STATUS_FETCHED
                succeeded += 1
            else:
                item["full_content"] = ""
                item["content_status"] = schemas.CONTENT_STATUS_FAILED
                if err:
                    item["fetch_error"] = err
                failed += 1

    attempted = succeeded + failed
    return {
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
        "success_rate": round(succeeded / attempted, 3) if attempted else 0.0,
        "avg_latency_sec": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        "latencies": [round(l, 2) for l in latencies],
    }


def truncate_reason(reason: str, max_chars: int = schemas.REASON_MAX_CHARS) -> str:
    """硬截断 reason 到 max_chars（兜底 scorer 不遵守上限的情况）。
    保留前 max_chars-1 字 + '…'。"""
    if not reason or len(reason) <= max_chars:
        return reason or ""
    return reason[:max_chars - 1].rstrip() + "…"


def merge_content_score(item: dict) -> None:
    """根据 content_status 合成最终 ai_score 到 item。

    规则：
    - fetched: ai_score = W_TITLE * title + W_CONTENT * content_score
    - failed: content_score = max(0, title_score - PENALTY)，再合成
    - not_attempted: ai_score = title_score（一轮分）

    顺带裁剪超长 reason（scorer 偶尔不遵守 40 字上限的兜底）。

    item 原地修改：可能写 content_score / ai_score / reason 字段。
    """
    # 兜底裁剪 reason
    if item.get("reason"):
        item["reason"] = truncate_reason(item["reason"])
    title = item.get("title_score")
    if not isinstance(title, (int, float)):
        # title_score 都没有，无法合成；保持原样
        return

    status = item.get("content_status", schemas.CONTENT_STATUS_NOT_ATTEMPTED)
    if status == schemas.CONTENT_STATUS_FETCHED:
        content = item.get("content_score")
        if not isinstance(content, (int, float)):
            # fetched 但二轮没给 content_score，降级当 failed 处理
            content = max(0, title - schemas.PENALTY_FAILED_FETCH)
            item["content_score"] = content
            item["content_status"] = schemas.CONTENT_STATUS_FAILED
    elif status == schemas.CONTENT_STATUS_FAILED:
        content = max(0, title - schemas.PENALTY_FAILED_FETCH)
        item["content_score"] = content
    else:  # not_attempted
        item["ai_score"] = round(title, 2)
        return

    ai = schemas.W_TITLE * title + schemas.W_CONTENT * content
    item["ai_score"] = round(ai, 2)
