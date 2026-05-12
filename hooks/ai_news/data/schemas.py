"""ai-news pipeline 数据契约 (Phase 1.1/1.2)。

scorer 输出 schema、ai-news.json 顶层段、各类枚举值在此集中定义。
其他模块（scorer prompt / Python 模块 / 前端）按这里统一字段名。
"""

# ---- topic_tags 封闭枚举（14 值） ----
# scorer 必须从这里挑 1-3 个，未知归 "other"。
TOPIC_TAGS = frozenset((
    "model_release",        # 大模型 / 主要 LLM 新版本
    "tool_release",         # 工具 / SDK / 框架发布
    "product_update",       # 产品功能升级
    "agent_workflow",       # agent / 工作流相关
    "coding_tool",          # 编码辅助 / Cursor / Codex / Copilot 等
    "paper",                # 论文 / 学术
    "benchmark",            # 评测 / 对比测试
    "tutorial",             # 教程 / 使用经验
    "infra",                # 算力 / GPU / 训练基础设施
    "policy",               # 政策 / 监管
    "business",             # 商业 / 融资 / 战略
    "community_discourse",  # 社区争议 / 行业观点
    "github_project",       # GitHub 项目（其实 github_trending 不走 scorer，备用）
    "other",                # 兜底
))

# ---- content_status 枚举 ----
CONTENT_STATUS_FETCHED = "fetched"            # Jina 抓取成功，content_score 基于正文
CONTENT_STATUS_FAILED = "failed"              # Jina 抓取失败，content_score = title_score - 1
CONTENT_STATUS_NOT_ATTEMPTED = "not_attempted"  # 非边界候选，未抓取
VALID_CONTENT_STATUS = frozenset((
    CONTENT_STATUS_FETCHED,
    CONTENT_STATUS_FAILED,
    CONTENT_STATUS_NOT_ATTEMPTED,
))

# ---- featured_mode 枚举 ----
FEATURED_MODE_NORMAL = "normal"                 # scorer + #5 + MMR 全跑通
FEATURED_MODE_PARTIAL = "partial"               # 部分源/正文失败但 MMR 正常
FEATURED_MODE_FALLBACK_NATIVE = "fallback_native"  # scorer 全挂，原生排序兜底

# ---- 边界候选选择参数 ----
TITLE_SCORE_BOUNDARY_LOW = 5   # 边界下界（含）
TITLE_SCORE_BOUNDARY_HIGH = 7  # 边界上界（含）
DEFAULT_BOUNDARY_CAP = 10      # 全局边界 cap
HARD_BOUNDARY_CAP = 12         # 硬上限
MIN_BOUNDARY_FETCH = 4         # 枯燥日补足下限（从全局 rank 6-15 补到 ≥4）

# ---- score 合成权重 ----
W_TITLE = 0.4
W_CONTENT = 0.6
PENALTY_FAILED_FETCH = 1.0  # 抓不到正文时 content_score = max(0, title_score - PENALTY)

# ---- MMR diversity 参数 ----
MMR_TARGET_N = 10
MMR_MIN_SCORE = 5.0

# 硬上限
MAX_PER_EVENT = 2
MAX_PER_TOPIC = 4
MAX_PER_SOURCE = 4

# 软惩罚阈值（达到这个数量后下一条扣分）
SOFT_TOPIC_AFTER = 2
SOFT_SOURCE_AFTER = 3

# 惩罚值
DUPLICATE_EVENT_PENALTY = 2.0      # 同 event_key 第 2 条扣分
SOFT_TOPIC_PENALTY = 0.8           # 同 topic 第 3 条起扣分
SOFT_SOURCE_PENALTY = 0.6          # 同 source 第 4 条扣分

# 加分
SIMONW_SOURCE_BONUS = 0.3          # simonw 是一手作者，加分
CHINESE_LANGUAGE_BONUS = 0.2       # 中文内容（用户偏好快读）加分
CHINESE_CJK_THRESHOLD = 0.3        # 标题+desc 中 CJK 字符占字母+CJK 比例 ≥ 0.3 视为中文

# ---- 不参与 MMR 的源 ----
# github_trending 永远 stage=cold，不走 scorer 也不进 featured
EXCLUDED_FROM_MMR = frozenset(("github_trending",))

# ---- scorer reason 长度上限 ----
REASON_MAX_CHARS = 40

# ---- 内容抓取参数（fetchers.py 用） ----
ARTICLE_TIMEOUT_SEC = 7
ARTICLE_MAX_CHARS = 3000
FETCH_MAX_WORKERS = 4

def is_valid_topic_tag(tag: str) -> bool:
    return tag in TOPIC_TAGS


def is_valid_content_status(status: str) -> bool:
    return status in VALID_CONTENT_STATUS


def normalize_topic_tags(tags) -> list:
    """清理 scorer 输出的 topic_tags：保留枚举内值，最多 3 个，空则 ["other"]."""
    if not isinstance(tags, (list, tuple)):
        return ["other"]
    out = [t for t in tags if isinstance(t, str) and t in TOPIC_TAGS][:3]
    return out if out else ["other"]


# ---- scorer 输出 schema 参考（注释形式） ----
# 一轮 scorer 输出（每源）:
# {
#   "source_id": "hackernews",
#   "items": [
#     {
#       "url": "...",
#       "title": "...",
#       "title_score": 6,         # 0-10
#       "content_score": null,    # 一轮无内容评分
#       "ai_score": 6,            # = title_score（一轮）
#       "event_key": "openai-agent-sdk-release",  # kebab slug
#       "topic_tags": ["agent_workflow", "tool_release"],
#       "reason": "≤40 字中文",
#       "content_status": "not_attempted"
#     }
#   ]
# }
#
# 二轮 scorer 输出（每源边界）:
# {
#   "source_id": "hackernews",
#   "items": [
#     {
#       "url": "...",
#       "content_score": 8,       # 基于正文重评
#       "ai_score": 7.6,          # = W_TITLE * title_score + W_CONTENT * content_score
#       "reason": "正文确认...",  # 二轮 reason 覆盖一轮
#       "content_status": "fetched"
#     }
#   ]
# }
#
# ai-news.json 顶层 schema 增量:
# {
#   "updated_at": "...",
#   "version": "...",
#   "stage_by_source": {...},
#   "sources": [...],
#   "featured_items": [          # 新增：跨源全局精选 10 条
#     {item 同 sources[].items[] 字段 + source 字段}
#   ],
#   "pipeline_metrics": {        # 新增：本轮 pipeline 观测指标
#     "featured_mode": "normal",
#     "wall_time_sec": 410,
#     "flags": {"boundary_fetch": true, "mmr": true},
#     "scorer": {"source_failures": []},
#     "boundary_fetch": {"attempted": 10, "succeeded": 7, "failed": 3, "success_rate": 0.7, "avg_latency_sec": 5.8},
#     "mmr": {"pool_size": 34, "selected_count": 10, "suppressed_duplicate_count": 5,
#             "max_event_count": 2, "max_topic_count": 4, "max_source_count": 4,
#             "source_counts": {}, "topic_counts": {}},
#     "quality": {"featured_avg_ai_score": 7.1, "raw_top10_avg_ai_score": 7.4,
#                 "reason_over_40_count": 0, "missing_event_key_count": 0}
#   }
# }
