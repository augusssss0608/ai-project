---
name: ai-news-fetch
description: AI 大事每日抓取 + 评分 + 摘要 + 分析 + 写入 + git push + TG 通知. Claude Code Routines 每日 cron 触发.
---

# AI 大事 v2 主编排

## 适用场景

**Only** 通过 Claude Code Routines 调用 (claude.ai/code 上的 scheduled remote agent, 每日 cron 触发). 触发即执行 `run_full_pipeline` 流程, 跑完后通过 PAT 直推 main.

调度由 Routines cron 接管 (推荐 `0 1 * * *` UTC = 10:00 JST). 不再走 /loop / ScheduleWakeup, sentinel 文件机制也已废弃.

环境前置 (Routine environment 必须设好, 缺一不可):
- env vars: `GITHUB_PAT` (fine-grained, 仅 ai-project + Contents:RW), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `THREADS_SESSION_JSON` (压成单行的 .threads-session.json 内容)
- network allowlist: 至少 `github.com`, `api.telegram.org`, `www.threads.com`, 各源 RSS / API endpoint
- sources: `git_repository` 绑 `https://github.com/augusssss0608/ai-project`, `allow_unrestricted_git_push: true`
- outcomes: `branches: ["main"]` (避免 stop hook 想 auto-PR 失败)
- allowed_tools: 必须含 `Agent` (派 news-scorer/summary/analysis), 加 `Bash`/`Read`/`Write`/`Edit`/`Glob`/`Grep`

## run_full_pipeline 编排

### §1 Pre-pipeline: git setup + pull

cloud routine 启动时 cwd 是 `/home/user/ai-project` (Anthropic auto-mount), 但 origin remote 默认指向 Anthropic 内置的本地 proxy, **proxy 不允许 push**. 必须先把 origin URL 改成走 PAT 直接连 github.com:

```bash
cd /home/user/ai-project
git config user.email 'ai-news-routine@cloud.local'
git config user.name 'ai-news-routine'
git remote set-url origin "https://x-access-token:${GITHUB_PAT}@github.com/augusssss0608/ai-project.git"
git pull --rebase origin main 2>&1 | tail -5
```

**为什么必须先 pull**: 用户在 mac dashboard 上点的 vote 写到 `cloud-sync/ai-news-feedback.json`, 通过 mac 的 git push 推到 main. 云端 routine 启动时拉一下能拿到最新反馈, 否则 stage 判定会基于过时数据.

如果 pull 失败 (网络 / 冲突): **直接 abort pipeline**, 发 TG 错误通知, 不继续 (避免 push 时把云端旧状态盖掉用户最新反馈).

### §2 run_full_pipeline 编排

#### 2.1 抓取层 + hard_filter + 源特定过滤 + URL 去重 (subprocess Python, 不用 AI)

**过滤顺序**: 抓取 → 源特定 filter (threads 走 `threads_loose_filter`, 其他源走 `hard_filter`) → 白名单 filter (github_trending 多一道 `claude_only_filter`) → dedup_filter (剔除 history.jsonl 已出现过的 URL, **github_trending 源跳过**).

dedup_filter 在所有 stage 之前就生效 (cold/mid/hot 都会去重), 用户 down 过的 URL 和已展示无反馈的 URL 都被剔除.

**github_trending 特殊规则**:
1. 只保留明确跟 Claude 生态相关的仓库 (Claude / Anthropic / MCP / claude-code / agent skill 等), 因为 GitHub 热榜 AI 内容太杂, 用户只关心 Claude 相关.
2. **不走 dedup_filter**. 仓库是存续实体, 每次上榜可能带着新的 star 增量 (日/周/月维度), 允许反复展示. history.jsonl 仍会 append github 条目以供 scorer 的隐式负例分析使用, 但不用于去重.

```bash
cd /home/user/ai-project && python3 -c "
import sys, json
sys.path.insert(0, 'hooks')
from ai_news.data.fetchers import fetch_one
from ai_news.data.filters import apply_hard_filter, apply_dedup_filter, apply_claude_only_filter, apply_threads_loose_filter
from ai_news.data.history import load_all_urls
from pathlib import Path
import yaml

SOURCES = ['hackernews', 'github_trending', 'simonw', 'threads']
BASE = Path('.claude/skills/ai-news-filter/sources')
known = load_all_urls()  # 本次 pipeline 写 history 之前加载, 天然不会把本次内容当重复
DEDUP_EXEMPT = {'github_trending'}  # 不走 URL 去重的源
out = []
for sid in SOURCES:
    cfg = yaml.safe_load(open(BASE / sid / 'fetcher.yaml'))
    r = fetch_one(sid, cfg)
    if r.get('items'):
        before_hard = len(r['items'])
        # 源特定主 filter: threads 宽松, 其他源走标准 hard_filter
        if sid == 'threads':
            r['items'] = apply_threads_loose_filter(r['items'])
        else:
            r['items'] = apply_hard_filter(r['items'])
        after_hard = len(r['items'])
        if sid == 'github_trending':
            r['items'] = apply_claude_only_filter(r['items'])
        after_src = len(r['items'])
        if sid not in DEDUP_EXEMPT:
            r['items'] = apply_dedup_filter(r['items'], known)
        after_dedup = len(r['items'])
        r['filter_stats'] = {'raw': before_hard, 'after_hard': after_hard, 'after_src': after_src, 'after_dedup': after_dedup}
    out.append(r)
open('/tmp/ai-news-raw.json', 'w').write(json.dumps(out, ensure_ascii=False))
print(f'fetched: {[(s[\"id\"], len(s.get(\"items\", [])), s.get(\"filter_stats\")) for s in out]}')
"
```

读 `/tmp/ai-news-raw.json` 得到 4 源的候选列表 (github 未去重, 其他已去重).

#### 2.2 判定每源 stage

用 `ai_news.data.feedback.load_feedback()` + `get_stage(source_id, feedback)` 对每源得 `cold|mid|hot`.

正确 import (路径写错会触发 ImportError, 不许 fallback 成 hardcode all-cold; 失败就停 pipeline):

```python
from ai_news.data.feedback import load_feedback, get_stage
```

**例外**: `github_trending` 源永远强制 `stage = 'cold'`, 忽略 `get_stage` 返回值. 原因见 2.3: github 是多维度榜单, scorer 的主观打分会破坏"按 star 真实 top"语义. `stage_by_source` 字典和 `sources[i].stage` 两处都写 'cold'.

#### 2.3 Feature flags (pipeline 行为开关)

读环境变量决定 #5 / #2 / featured_items 是否启用，默认全开：

```python
import os
ENABLE_BOUNDARY_FETCH = os.environ.get("ENABLE_BOUNDARY_FETCH", "1") != "0"
ENABLE_MMR = os.environ.get("ENABLE_MMR", "1") != "0"
ENABLE_FEATURED_ITEMS = os.environ.get("ENABLE_FEATURED_ITEMS", "1") != "0"
```

- `ENABLE_BOUNDARY_FETCH=0`: 跳过 §2.3b/§2.3c，scorer 只用标题，所有 item `content_status=not_attempted`
- `ENABLE_MMR=0`: 跳过 §2.3d，featured 退化为按 `ai_score desc` 取 top10
- `ENABLE_FEATURED_ITEMS=0`: 完全回旧架构，不写 `featured_items` 字段，前端走源 tab

灰度顺序：先 `ENABLE_FEATURED_ITEMS=0`（影子模式跑通），再 `=1` 但 `ENABLE_BOUNDARY_FETCH=0/ENABLE_MMR=0`，最后全开。

#### 2.3a 一轮 title scorer (mid / hot 源, 输出全候选 scored pool)

**Cold 源跳过 scorer**, 直接 items[:10] 作为该源 tab 展示 (按原生排序).

**github_trending 源永远按 cold 行为处理, 但不截 items[:10]**: github 是多维度榜单 (日/周/月/总), 每条 item 带 `dimension` 字段, filter 后的全部 items 都要保留, 否则前端切到 "总" 维度会看到空. scorer 对 github 的"按 star 真实 top"语义没意义, 所以无论反馈多少也不走 scorer. **github 也永远不进 featured_items / MMR**.

对每个 mid/hot 源:
1. Write `/tmp/ai-news-scorer-{sid}-{ts}.json`, 内容 JSON:
   ```json
   {
     "source_id": "hackernews",
     "stage": "mid",
     "mode": "title",
     "source_md": "<sources/hackernews/source.md 完整内容>",
     "examples_md": "<build_examples_inline() 输出>",
     "candidates": [{"title":"...","url":"...","desc":"...","score":243,"comments":87}]
   }
   ```
2. 在**一次 message 内**用 `Agent` tool 并行发 N 次 (N = mid/hot 源数量):
   - `subagent_type: news-scorer`
   - `model: claude-haiku-4-5`
   - `prompt: "你是 news-scorer. 读 /tmp/ai-news-scorer-{sid}-{ts}.json, 模式 title, 打分后写 /tmp/ai-news-scored-{sid}-{ts}.json"`
3. 主 agent 等所有 scorer 返回, 读每个 output 文件, **保留所有候选**（不再截 Top N，给后续 #2 MMR 选择空间）。

每条 scored item 含: `title_score / ai_score(一轮等同 title_score) / event_key / topic_tags / reason / content_status="not_attempted"`. 见 `.claude/agents/news-scorer.md` 与 `hooks/ai_news/data/schemas.py` 字段定义.

**失败处理**:
- 单源 scorer 失败: 该源退化为 cold (items[:10] 原生排序), 该源不进 MMR
- 多源失败: MMR 池缩小，可能选不到 10 条 → §2.3d 兜底
- 全部失败: featured_mode 标记 `fallback_native`, MMR 跳过，featured = 各源 round-robin 拼凑

#### 2.3b 边界候选选择 + 抓正文 (#5, subprocess Python)

仅当 `ENABLE_BOUNDARY_FETCH=True` 跑此步。

```python
import sys; sys.path.insert(0, "hooks")
from ai_news.data.content_fetcher import select_boundary_candidates, fetch_boundary_contents

# scored_pool = 所有 mid/hot 源 §2.3a 输出合并 (含 source 字段)
boundary = select_boundary_candidates(scored_pool)
boundary_metrics = fetch_boundary_contents(boundary)
# boundary 每项原地 append: full_content / content_status / fetch_latency_sec
```

选边界规则: `title_score in [5,7]`, 全局 cap 10 (硬上限 12), 不足 min_fetch=4 时从 rank 6-15 补足。详见 `schemas.py`。

抓取: Jina Reader 优先, `ThreadPoolExecutor(max_workers=4)`, timeout 7s, max 3000 字。失败项 `content_status=failed` + `content_score = title_score - 1`。

**失败处理**: Jina 全部失败 → 所有边界项走 penalty 路径, §2.3c 仍跑 (输入空 full_content 时降级)。

#### 2.3c 二轮 content scorer (按源分组并行, 仅边界候选)

仅当 `ENABLE_BOUNDARY_FETCH=True` 且 boundary 非空跑此步。

按 source_id 把 boundary 候选分组, 对每组 (仅有 `content_status=fetched` 的):
1. Write `/tmp/ai-news-scorer-deep-{sid}-{ts}.json`, JSON:
   ```json
   {
     "source_id": "hackernews",
     "stage": "<mid|hot>",
     "mode": "content",
     "source_md": "<source.md>",
     "examples_md": "<build_examples_inline()>",
     "candidates": [
       {
         "url": "...", "title": "...", "desc": "...",
         "title_score": 6, "first_reason": "...",
         "event_key": "...", "topic_tags": [...],
         "full_content": "..."
       }
     ]
   }
   ```
2. **一次 message 内** Agent tool 并行发 N 次:
   - `subagent_type: news-scorer`
   - `prompt: "你是 news-scorer. 读 /tmp/ai-news-scorer-deep-{sid}-{ts}.json, 模式 content, 写 /tmp/ai-news-scored-deep-{sid}-{ts}.json"`
3. 读 output, 每条返回: `content_score / reason (覆盖一轮) / content_status="fetched"`. Python 合并回 scored_pool。

**失败处理**: 某源二轮失败 → 该源边界项保留一轮 reason, `content_status` 改 `failed`, content_score = title_score - 1。

#### 2.3d Python 合并 + 全局 MMR (#2)

```python
from ai_news.data.content_fetcher import merge_content_score
from ai_news.data.diversity import mmr_select, compute_quality_metrics

# 1. 合并 content_score 到 ai_score (per item)
for it in scored_pool:
    merge_content_score(it)  # 原地更新 ai_score

# 2. 全局 MMR 选 featured_items
if ENABLE_MMR:
    featured, suppressed, mmr_metrics = mmr_select(scored_pool, target_n=10)
else:
    # flag 关 → 简单按 ai_score desc 取 top 10
    eligible = [it for it in scored_pool if it.get("source") != "github_trending"]
    featured = sorted(eligible, key=lambda x: x.get("ai_score", 0), reverse=True)[:10]
    suppressed, mmr_metrics = [], {"pool_size": len(eligible), "selected_count": len(featured)}

# 3. 质量对照
raw_top10 = sorted(
    [it for it in scored_pool if it.get("source") != "github_trending"],
    key=lambda x: x.get("ai_score", 0), reverse=True
)[:10]
quality_metrics = compute_quality_metrics(featured, raw_top10)
```

**失败处理**: 池子选不够 10 → mmr_select 自动放宽 MIN_SCORE; 仍不够允许 < 10 条, 不 abort。

#### 2.4 分批派 news-summary × featured_items

**只对 featured_items（≤10 条）跑 summary**。各源 tab 内的非 featured 条目用原 `desc` 兜底（或为空），不再每条跑 summary，**省 ~30 次 haiku 调用**。

每批 **10 个并行** (一次 message 发 10 个 Agent tool call), 通常 1 批跑完.

每个 prompt:
```
你是 news-summary. title: "..." url: "..." 把摘要写到 /tmp/ai-news-summary-{idx}-{ts}.json
```

主 agent 读 output, 把 summary 合并回 featured_items 主列表.

**threads 源 featured item 例外**: threads 的 post 本身是短文, AI 复述损失原汁原味, 不派 summary. 直接把 `it.desc` (已截 300 字符) 拷到 `it.summary`. 前端按源 ID 检测后用 "原文" label 渲染.

**ENABLE_FEATURED_ITEMS=0 时**: 退化为对每源 top items[:10] 跑（旧行为）, 但量级一样.

#### 2.5 分批派 news-analysis × featured_items top 5

**只对 featured_items top 5 跑 analysis**（按 ai_score 取前 5）。Opus 慢 + 成本高, 限制 top 5 控制 wall time。

每批 **3 个并行**, 跑 ~2 批.

每个 prompt:
```
你是 news-analysis. title: "..." url: "..."
source_id: "<featured item 的源>"
topic_tags: [...]
reason: "<scorer 一/二轮 reason>"
content_status: "<fetched|failed|not_attempted>"
workspace_context_path: "/Users/augus/Desktop/开发项目/live_app/CLAUDE.md"
把分析写到 /tmp/ai-news-analysis-{idx}-{ts}.json
```

**云端兼容性提示**: 上面那个 `workspace_context_path` 是 mac 上 live_app 仓库路径, 在 cloud routine 内**不存在**. 子代理读不到时把 `workspace_help` 和 `claude_usage` 字段填 "无相关" 优雅降级.

主 agent 读 output, 合并回 featured_items.

**ENABLE_FEATURED_ITEMS=0 时**: 退化为对每源 top items[:5] 跑（旧行为, ~12 批）.

#### 2.6 写 ai-news.json + history.jsonl

**payload schema 必须严格按以下结构** (spec §10, 不许偷懒平铺 / 改字段名):

```python
payload = {
    "updated_at": "2026-04-22T14:45:00+09:00",   # ISO 带时区, 本次 pipeline 启动时间
    "version": 2,
    "stage_by_source": {
        "hackernews": "cold",        # 'cold' | 'mid' | 'hot' 三值之一
        "github_trending": "cold",   # github 永远强制 cold, 见 §2.2
        "simonw": "cold",            # Simon Willison 博客, 走 get_stage 正常判定
        "threads": "cold",           # Threads For You, 冷启动, 走 get_stage 正常判定
    },
    "sources": [                     # list, 不是 dict! 顺序: HN / GitHub / Simon / Threads
        {
            "id": "hackernews",
            "label": "Hacker News",
            "source_url": "https://news.ycombinator.com/",
            "updated_at": "2026-04-22T14:45:00+09:00",
            "stage": "cold",
            "items": [
                {
                    "title": "...",
                    "url": "...",
                    "desc": "...",
                    "score": 484,              # HN points / GitHub 总 stars, 无则 null
                    "comments": 276,           # HN 评论数, 无则 null
                    "ts": "2026-04-21T03:43:03Z",
                    "ai_score": null,          # cold 阶段 null, mid/hot 才有 0-10 分
                    "reason": null,            # scorer 给的中文理由, ≤40 字, cold 阶段 null
                    "title_score": null,       # mid/hot scorer 标题分, cold 阶段 null
                    "content_score": null,     # 二轮 scorer 正文分, 边界候选才有, 否则 null
                    "content_status": "not_attempted",  # 'fetched' | 'failed' | 'not_attempted'
                    "event_key": null,         # mid/hot 才有 kebab slug; cold/null
                    "topic_tags": [],          # mid/hot 才有, 见 schemas.TOPIC_TAGS 14 值
                    "summary": "news-summary 的中文摘要, 120-150 字 (不超过 150, 尽量塞满 viewport)",
                    "workspace_help": "news-analysis 给 workspace 的建议, 60-80 字 (不超过 80), 或 '无相关'",
                    "claude_usage": "news-analysis 给 Claude Code 使用的建议, 60-80 字 (不超过 80), 或 '无相关'",
                    "hn_url": "https://news.ycombinator.com/item?id=...",  # HN only, 其他源空串
                    "summary_error": "",       # 子代理失败时填 error 原因, 否则空串
                }
            ],
            "error": null,            # 该源抓取/pipeline 失败时填 error 字符串
        }
    ],
}
```

**github_trending 源的 item 必须额外带 7 个字段** (前端切维度 + 徽章渲染依赖, 缺了就没法切榜和显示 star):

```python
# 每个 github item 额外加:
"daily_stars": 1023,            # fetcher 返回的 daily_stars, int
"weekly_stars": 1381,           # fetcher 返回的 weekly_stars, int
"monthly_stars": 0,             # fetcher 返回的 monthly_stars, int
"total_stars_int": 8087,        # fetcher 返回的 total_stars_int, int
"stars": "8,087",               # 原始字符串, fetcher 返回的 stars
"lang": "TypeScript",           # 仓库语言, fetcher 返回的 lang, 可能为空串
"dimension": "daily",           # 'daily' | 'weekly' | 'monthly' | 'total' — 该 item 属于哪个榜单
```

**`dimension` 字段是 github 源的核心数据模型**:
- fetcher (`fetch_github_trending_multi`) 返回扁平 list, 4 个独立榜单 (日/周/月/总) 各自独立取 top, 每条 item 标识属于哪个维度
- 同一仓库可能在多个维度各保留一条 (比如 daily top + weekly top 都有 claude-context, 会有 2 条)
- 前端按 `dimension` 过滤展示, 切换左栏 github 按钮就循环切 daily → weekly → monthly → total
- 组装时直接透传 fetcher 返回的 `dimension`, 不要合并 / 去重

组装时从 fetcher 的 item 直接透传这 7 个字段, 不要遗漏 / 改名 / 合并.

**禁止项 (reviewer 反馈, 防止 schema 偏离)**:
- 不许用 `generated_at` 代替 `updated_at`
- 不许把 `sources` 写成 dict (必须 list, items 嵌套在 source 内)
- 不许把 `items` 放顶层 (必须嵌套在 `sources[].items`)
- 不许把 workspace_help + claude_usage 合并成一个 analysis 字段
- 不许把 github 的 daily/weekly/monthly/total stars 合并成单一字段, 前端要分别读

**新增顶层段** (ENABLE_FEATURED_ITEMS=True 时):

```python
payload["featured_items"] = [
    # 来自 §2.3d mmr_select 输出, 不含 github
    # 每项字段同 sources[].items[], 额外加:
    {
        # ...原 item 字段...
        "source": "hackernews",    # 标明来源, 前端 featured tab 按源分组用
    }
]

payload["pipeline_metrics"] = {
    "featured_mode": "normal",       # 'normal' | 'partial' | 'fallback_native'
    "wall_time_sec": 410,
    "flags": {
        "boundary_fetch": ENABLE_BOUNDARY_FETCH,
        "mmr": ENABLE_MMR,
        "featured_items": ENABLE_FEATURED_ITEMS,
    },
    "scorer": {
        "source_failures": [],       # 列出 §2.3a 失败的源 id
    },
    "boundary_fetch": boundary_metrics,  # 来自 fetch_boundary_contents()
    "mmr": mmr_metrics,                  # 来自 mmr_select()
    "quality": quality_metrics,          # 来自 compute_quality_metrics()
}
```

写入前可选清掉 featured_items 内部巨大的 `full_content` 字段（前端不需要）。

**组装后, 按以下顺序写入**:

```python
from ai_news.data.io import write_ai_news_atomic
from ai_news.data.history import append_items

write_ai_news_atomic(payload)
# history.jsonl: 每条 item 一行, 格式 spec §11.1
append_items([
    {"ts": payload["updated_at"], "source": src["id"], "url": it["url"],
     "title": it["title"], "desc": it["desc"]}
    for src in payload["sources"] for it in src["items"]
])
```

**写完后必须自检**:
```python
import json
from ai_news.data.io import AI_NEWS_PATH  # repo-relative, mac/cloud 都自动对
data = json.load(open(AI_NEWS_PATH))
assert "updated_at" in data and "sources" in data, "schema 错误: 顶层缺字段"
assert isinstance(data["sources"], list), f"sources 必须是 list, got {type(data['sources'])}"
for src in data["sources"]:
    assert "items" in src and isinstance(src["items"], list), f"source {src.get('id')} 缺 items list"
    for it in src["items"]:
        for k in ("title", "url", "summary", "workspace_help", "claude_usage"):
            assert k in it, f"item 缺字段 {k}: {it.get('title', '')[:40]}"
        # github 源必须带 7 个额外字段, 否则前端切维度 / star 徽章不工作
        if src["id"] == "github_trending":
            for k in ("daily_stars", "weekly_stars", "monthly_stars", "total_stars_int", "stars", "lang", "dimension"):
                assert k in it, f"github item 缺字段 {k}: {it.get('title', '')[:40]}"
            assert it["dimension"] in ("daily", "weekly", "monthly", "total"), \
                f"github item dimension 非法值: {it.get('dimension')}"
print("schema 自检通过")
```
自检失败就不要发 TG, 写 log 后停止 pipeline (不覆盖旧 ai-news.json 已由 write_atomic 保证, 也不要 git push, 让云端工作树自动随 session 销毁).

#### 2.6.1 git commit + push (cloud-sync 数据回写)

self-check 通过后, 把这次 pipeline 写入的 `cloud-sync/` 推回 github main:

```bash
cd /home/user/ai-project
git add cloud-sync/
git diff --cached --quiet && echo "no changes to commit" || (
  git commit -m "data(ai-news): pipeline run $(date -u +%Y-%m-%dT%H:%MZ)" && \
  git push origin HEAD:main
)
```

**关键约束**:
- §1 已经把 origin URL 改成 PAT 形式, 这里不需要再改
- `git diff --cached --quiet` 检查避免空 commit (理论上 ai-news.json updated_at 每次都变所以一定有 diff, 但保险起见)
- push 失败时 (403 / network / conflict) **不阻塞后续 TG**, 记 stderr, 让用户从 TG 注意到失败信号; 数据本身已写入云端工作树, 但工作树会随 session 销毁, 所以 push 失败这一天等于 pipeline 白跑
- evolve 修改 source.md / examples.md 由 §2.8 末尾再单独 commit + push (见下面)

#### 2.7 发 TG 通知

**不能用 MCP plugin** (`mcp__plugin_telegram_telegram__reply`): plugin 内置 orphan watchdog, 在云端 routine 里也不一定可用. 改用独立脚本 `hooks/tg_notify.py`, 它直接调 Telegram Bot API + 从 env var 读 token, 跨 mac 和云端都能跑.

```bash
cd /home/user/ai-project && python3 hooks/tg_notify.py --stdin <<EOF
[ai-news] 已刷新 {total} 则
HN {n1} · GitHub {n2} · Simon {n3} · Threads {n4}
阶段: HN {s1} · GitHub {s2} · Simon {s3} · Threads {s4}
dashboard: http://localhost:38080/#news
EOF
```

`tg_notify.py` 优先读 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` env vars, 没有则回退本地 `.env` 文件 (mac 路径). 脚本失败时退出码非 0, 打印错误到 stderr (不含 token). 失败 graceful skip (写 log 不阻塞主流程).

#### 2.8 Evolve 检查 (每源)

对每个 hot 源:
1. 读 source.md frontmatter `last_evolve_at`
2. 统计 `last_evolve_at` 之后该源新增反馈数
3. 若 >= 20:
   - `ai_news.data.evolve.load_frontmatter()` 读 `evolve_count` (= N)
   - `ai_news.data.evolve.backup_source(source_md_path, N)`
   - 组装 evolve 输入 JSON, Write 到 `/tmp/ai-news-evolve-{sid}-{ts}.json`
   - 派 evolve-source-preferences subagent (model: claude-opus-4-7)
   - 读 output, 记 `ai_news.data.evolve.write_evolve_log(entry)`
   - 发 TG 通知 (同 2.7, 用 `hooks/tg_notify.py`, 不用 MCP plugin)

**evolve 修改了 source.md / examples.md 后必须 git push** (这些是仓内代码, 不是 cloud-sync 数据, 但 cloud 工作树修改不 push 走的话, 下次 routine 启动会从 main fresh clone 再次拿到旧 source.md, evolve 等于白做):

```bash
cd /home/user/ai-project
git add .claude/skills/ai-news-filter/sources/
git diff --cached --quiet && echo "no evolve changes" || (
  git commit -m "evolve(ai-news): source.md update from $(date -u +%Y-%m-%d) pipeline" && \
  git push origin HEAD:main
)
```

如果本次 pipeline 没有源进入 evolve 触发条件, 这一段 git push 是空操作 (diff --cached --quiet 走通).

#### 2.9 清理 (临时文件 + cloud session 工作分支)

```bash
# /tmp 中间产物
rm -f /tmp/ai-news-scorer-*-{ts}.json /tmp/ai-news-scored-*-{ts}.json \
      /tmp/ai-news-summary-*-{ts}.json /tmp/ai-news-analysis-*-{ts}.json \
      /tmp/ai-news-evolve-*-{ts}.json /tmp/ai-news-raw.json

# cloud session 工作分支自删 (避免 Anthropic stop hook auto-push 留下孤儿 main-XXX 分支)
# 注意: 必须在所有 git push to main 之后, 这是最后一个 git 动作.
# regex 兜底, 只删 main-<suffix> 形式的 session 分支, 不动 main 本身
cd /home/user/ai-project
session_branch=$(git branch --show-current)
if [[ "$session_branch" =~ ^main-[A-Za-z0-9]+$ ]]; then
  git push origin --delete "$session_branch" 2>&1 | tail -3 || echo "session-branch self-delete failed (non-fatal)"
else
  echo "skip session-branch cleanup: branch=$session_branch (not main-<suffix>)"
fi
```

**注意 stop hook 时序**: Anthropic stop hook 在 agent 结束后异步运行, 试图把 working tree 推到 outcomes 配置的分支. 如果它的 push 时机晚于此处的自删, 那个孤儿分支会被它复活. 先试看效果; 如果 main-XXX 仍然出现, 改用本地 mac cron 定期 `git push origin --delete` 清理.

## 错误降级 / 失败矩阵

| 失败点 | 兜底策略 | `featured_items` 能出吗 |
|---|---|---|
| §2.1 某源 fetcher 失败 | 该源 `error` 写入 source; 其他源继续 | 能（来自其他源） |
| §2.1 全部 fetcher 失败 | 不覆盖旧 ai-news.json, 发 TG 错误 | 不能, 本轮 abort |
| §2.3a 某源一轮 scorer 失败 | 该源退化为 cold (items[:10] 原生排序); 该源不进 MMR | 能, 用其他 scored 源 |
| §2.3a 多源 scorer 失败 | MMR 只用成功源; 池子可能不足 10 → §2.3d 放宽 | 能, 可能 < 10 |
| §2.3a 全部 scorer 失败 | `featured_mode="fallback_native"`; featured 用非 github 源各取 top items[:3] round-robin | 能 (但不是 AI 精选) |
| §2.3b Jina 部分失败 | 失败项 `content_status=failed`, content_score = title_score - 1 | 能 |
| §2.3b Jina 全部失败 | 所有边界项走 penalty; §2.3c 跳过, 直接合并到 MMR | 能 |
| §2.3c 某源二轮 scorer 失败 | 该源边界项 `content_status=failed` + penalty; 保留一轮 reason | 能 |
| §2.3c 全部二轮失败 | #5 退化为 penalty-only, MMR 照常跑 | 能 |
| §2.3d MMR 选不够 10 | 自动放宽 MIN_SCORE; 仍不够允许 < 10 条 | 能, 可能 < 10 |
| §2.4 summary 单条失败 | 该条 `summary_error` 写原因; summary 用 desc 兜底 | 能 |
| §2.4 summary 全部失败 | featured 仍写出, 前端用 desc 渲染 | 能 |
| §2.5 analysis 单条失败 | 该条 `workspace_help/claude_usage` 填 "无相关" | 能 |
| §2.5 analysis 全部失败 | featured 仍写出, analysis 字段统一 "无相关" | 能 |
| §2.6 写 ai-news.json schema 自检失败 | 不覆盖旧文件, 发 TG 错误 | 不能, 本轮 abort |
| §2.7 git push 失败 | 本地已写但云端不可见; 发 TG 错误 | 本地能, 发布失败 |
| §2.8 TG 断连 | 不阻塞主流程, 写 log | 能 |

**关键原则**:
- scorer / content / MMR 失败不应该导致整轮 abort
- 只有 fetcher 全挂 / schema 自检失败 / 写 atomic 失败 才 abort（不覆盖旧 ai-news.json）
- `featured_mode` 三态明确标识本轮质量: `normal / partial / fallback_native`

## 模型分工强制

| 调用点 | subagent | model |
|---|---|---|
| 评分 | news-scorer | claude-haiku-4-5 |
| 摘要 | news-summary | claude-haiku-4-5 |
| 分析 | news-analysis | claude-opus-4-7 |
| evolve | evolve-source-preferences | claude-opus-4-7 |

**主 agent 绝不自己打分/摘要/分析**. 统统派 subagent.
