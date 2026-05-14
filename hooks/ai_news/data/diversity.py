"""#2 全局批级 diversity (MMR 贪心) + utility 计算 + 配额限制。

调用顺序（pipeline §2.4d）：
1. 收集所有源的 scored items（已合成 ai_score 含 #5 正文权重）
2. 排除 EXCLUDED_FROM_MMR 源（github_trending）
3. mmr_select(pool) → featured_items + suppressed_log + metrics

设计要点（见 schemas.py）：
- utility = ai_score + source_bonus + language_bonus - duplicate_penalty - topic_penalty - source_penalty
- 三层硬上限：同 event_key ≤ 2、同 topic ≤ 4、同 source ≤ 4
- 三层软惩罚：event 第 2 条 -2.0、topic 第 3 条起 -0.8、source 第 4 条 -0.6
- 加分：中文 +0.2
- 兜底：池子选不够 target_n 时放宽 MIN_SCORE
"""
from collections import defaultdict

from . import schemas


# CJK 范围（覆盖中日韩统一汉字基本区，足够判中文）
_CJK_LO = "一"
_CJK_HI = "鿿"


def is_chinese_item(item: dict) -> bool:
    """标题 + desc 前 300 字符 CJK 占比 >= threshold 视为中文。"""
    text = ((item.get("title") or "") + " " + (item.get("desc") or ""))[:300]
    if not text:
        return False
    cjk = sum(1 for ch in text if _CJK_LO <= ch <= _CJK_HI)
    letters = sum(1 for ch in text if ch.isalnum() or _CJK_LO <= ch <= _CJK_HI)
    if letters == 0:
        return False
    return cjk / letters >= schemas.CHINESE_CJK_THRESHOLD


def _normalize_event_key(item: dict) -> str:
    """空 event_key 用 url:<url> 兜底，保证 dedup 计数 key 唯一。"""
    ek = (item.get("event_key") or "").strip()
    if ek:
        return ek
    return "url:" + (item.get("url") or "")


def _candidate_allowed(item: dict, event_count, topic_count, source_count) -> bool:
    """硬上限：event ≤ 2、topic ≤ 4、source ≤ 4，任一超过即禁。"""
    ek = _normalize_event_key(item)
    if event_count[ek] >= schemas.MAX_PER_EVENT:
        return False
    if source_count[item.get("source", "")] >= schemas.MAX_PER_SOURCE:
        return False
    tags = item.get("topic_tags") or ["other"]
    for tag in tags:
        if topic_count[tag] >= schemas.MAX_PER_TOPIC:
            return False
    return True


def _utility(item: dict, event_count, topic_count, source_count) -> float:
    """MMR utility 公式（见 schemas.py 注释段）。"""
    ek = _normalize_event_key(item)
    src = item.get("source", "")
    tags = item.get("topic_tags") or ["other"]
    ai_score = item.get("ai_score", 0) or 0

    # 同 event 第 2 条扣分（第 1 条计数=0 时不扣）
    duplicate_penalty = (
        schemas.DUPLICATE_EVENT_PENALTY if event_count[ek] >= 1 else 0.0
    )

    # 同 topic：达 SOFT_TOPIC_AFTER 后扣分（任一 tag 命中即触发）
    topic_penalty = 0.0
    for tag in tags:
        if topic_count[tag] >= schemas.SOFT_TOPIC_AFTER:
            topic_penalty = max(topic_penalty, schemas.SOFT_TOPIC_PENALTY)

    # 同 source 软惩罚
    source_penalty = (
        schemas.SOFT_SOURCE_PENALTY
        if source_count[src] >= schemas.SOFT_SOURCE_AFTER
        else 0.0
    )

    # 加分
    language_bonus = schemas.CHINESE_LANGUAGE_BONUS if is_chinese_item(item) else 0.0

    return ai_score + language_bonus - duplicate_penalty - topic_penalty - source_penalty


def mmr_select(
    pool: list,
    target_n: int = schemas.MMR_TARGET_N,
    min_score: float = schemas.MMR_MIN_SCORE,
) -> tuple:
    """全局 MMR 贪心选 featured_items。

    pool: 跨源 scored items 列表，每项需含 source, ai_score, event_key, topic_tags
    返回: (selected, suppressed, metrics)
      - selected: 入选条目（同序）
      - suppressed: 被压条目（含原因，仅用于调试 log）
      - metrics: mmr 阶段观测指标，写入 pipeline_metrics.mmr
    """
    # 过滤排除源 + 无效项
    eligible = [
        it for it in pool
        if it.get("source") not in schemas.EXCLUDED_FROM_MMR
        and isinstance(it.get("ai_score"), (int, float))
    ]
    pool_size = len(eligible)

    # 兜底：池子大 score 低时放宽 MIN_SCORE
    over_threshold = [it for it in eligible if it["ai_score"] >= min_score]
    if len(over_threshold) < target_n and eligible:
        # 用所有 eligible，让贪心自己选
        candidates_init = sorted(eligible, key=lambda x: x["ai_score"], reverse=True)
    else:
        candidates_init = over_threshold

    selected = []
    suppressed = []
    event_count = defaultdict(int)
    topic_count = defaultdict(int)
    source_count = defaultdict(int)

    remaining = list(candidates_init)

    while len(selected) < target_n and remaining:
        # 计算所有可选项的 utility，取最高
        scored_candidates = []
        for it in remaining:
            if not _candidate_allowed(it, event_count, topic_count, source_count):
                continue
            u = _utility(it, event_count, topic_count, source_count)
            scored_candidates.append((u, it))

        if not scored_candidates:
            break

        # tie-break: utility desc, ai_score desc
        scored_candidates.sort(
            key=lambda x: (x[0], x[1].get("ai_score", 0)),
            reverse=True,
        )
        _, picked = scored_candidates[0]
        selected.append(picked)
        remaining = [it for it in remaining if it is not picked]

        # 更新计数
        event_count[_normalize_event_key(picked)] += 1
        source_count[picked.get("source", "")] += 1
        for tag in (picked.get("topic_tags") or ["other"]):
            topic_count[tag] += 1

    # 标记被压（仅 event_key 重复 / 配额满的）作为调试 log
    selected_urls = {it.get("url") for it in selected}
    for it in eligible:
        if it.get("url") in selected_urls:
            continue
        ek = _normalize_event_key(it)
        if event_count[ek] >= schemas.MAX_PER_EVENT:
            suppressed.append({
                "url": it.get("url", ""),
                "title": it.get("title", ""),
                "source": it.get("source", ""),
                "reason": "duplicate_event",
                "event_key": ek,
            })

    metrics = {
        "pool_size": pool_size,
        "selected_count": len(selected),
        "suppressed_duplicate_count": len(suppressed),
        "max_event_count": max(event_count.values()) if event_count else 0,
        "max_topic_count": max(topic_count.values()) if topic_count else 0,
        "max_source_count": max(source_count.values()) if source_count else 0,
        "source_counts": dict(source_count),
        "topic_counts": dict(topic_count),
    }
    return selected, suppressed, metrics


def compute_quality_metrics(featured: list, raw_top10: list) -> dict:
    """对比 featured 和未做 #2 的 raw top10 的质量差异，写入 pipeline_metrics.quality。

    raw_top10: 假设 pool 按 ai_score desc 直接取 10（不做 diversity）作对照。
    """
    def avg(items):
        if not items:
            return 0.0
        scores = [it.get("ai_score", 0) or 0 for it in items]
        return round(sum(scores) / len(scores), 2)

    reason_over_40 = sum(
        1 for it in featured
        if len(it.get("reason") or "") > schemas.REASON_MAX_CHARS
    )
    missing_event_key = sum(
        1 for it in featured
        if not (it.get("event_key") or "").strip()
    )
    return {
        "featured_avg_ai_score": avg(featured),
        "raw_top10_avg_ai_score": avg(raw_top10),
        "reason_over_40_count": reason_over_40,
        "missing_event_key_count": missing_event_key,
    }
