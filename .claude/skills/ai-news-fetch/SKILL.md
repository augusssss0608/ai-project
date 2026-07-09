---
name: ai-news-fetch
description: AI 大事每日抓取 + 评分 + 摘要 + 分析 + 写入 + git push + TG 通知. Claude Code Routines 每日 cron 触发.
---

# AI 大事 v2 主编排

## 适用场景

**Only** 通过 Claude Code Routines 调用 (claude.ai/code 上的 scheduled remote agent, 每日 cron 触发). 触发即执行 `run_full_pipeline` 流程, 跑完后通过 PAT 直推 main.

调度由 Routines cron 接管 (推荐 `0 1 * * *` UTC = 10:00 JST). 不再走 /loop / ScheduleWakeup, sentinel 文件机制也已废弃.

环境前置 (Routine environment 必须设好, 缺一不可):
- env vars: `GITHUB_PAT` (fine-grained, 仅 ai-project + Contents:RW), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `THREADS_SESSION_JSON` (压成单行的 .threads-session.json 内容), `JINA_API_KEY` (github total 维度与 trending 兜底都走 r.jina.ai; 匿名池会被其他用户的滥用连坐封禁 github.com, 带 key 走专属配额不受影响. 仓库是公开的, key 不能写进代码)
- network allowlist: 至少 `github.com`, `api.telegram.org`, `www.threads.com`, 各源 RSS / API endpoint
- sources: `git_repository` 绑 `https://github.com/augusssss0608/ai-project`
- outcomes: `branches: ["main"]` — 这项配错成工作分支名时, cloud session 会注入"只准推该工作分支"的指令, 数据就滞留在 epic 分支上不了 main (2026-07-09 曾因配成 `["claude/epic-goodall"]` 实际发生, 已修正; 改 routine 配置用 RemoteTrigger update)
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

SOURCES = ['hackernews', 'github_trending', 'threads']
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

#### 2.3 评分方案：title scorer + 边界正文 scoring

mid/hot 源跑 title scorer → 边界候选抓正文重评 → 合并 content_score 到 ai_score, 用于各源 tab 内排序 (高分在前).

如果上线后想关掉某一段，**直接 `git revert` 对应 commit**（单一 commit 便于回滚）。

#### 2.3a 一轮 title scorer (mid / hot 源, 输出全候选 scored pool)

**Cold 源跳过 scorer**, 直接 items[:10] 作为该源 tab 展示 (按原生排序).

**github_trending 源永远按 cold 行为处理, 但不截 items[:10]**: github 是多维度榜单 (日/周/月/总), 每条 item 带 `dimension` 字段, filter 后的全部 items 都要保留, 否则前端切到 "总" 维度会看到空. scorer 对 github 的"按 star 真实 top"语义没意义, 所以无论反馈多少也不走 scorer.

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
3. 主 agent 等所有 scorer 返回, 读每个 output 文件, **保留所有候选**, 跨源去重交给 §2.3e。scorer 输出含 event_key, 后续按 event_key 跨源压缩重复事件, 不在这里截 Top N。

每条 scored item 含: `title_score / ai_score(一轮等同 title_score) / event_key / topic_tags / reason / content_status="not_attempted"`. 见 `.claude/agents/news-scorer.md` 与 `hooks/ai_news/data/schemas.py` 字段定义.

**失败处理**:
- 单源 scorer 失败: 该源退化为 cold (items[:10] 原生排序)
- 全部失败: 所有 mid/hot 源都退化为 cold, pipeline 继续

#### 2.3b 边界候选选择 + 抓正文 (#5, subprocess Python)

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

**失败处理**: Jina 全部失败 → 所有边界项走 penalty 路径, §2.3c 仍跑 (输入空 full_content 时降级), 各源 tab 仍能按 title_score 排序。

#### 2.3c 二轮 content scorer (按源分组并行, 仅边界候选)

仅当 boundary 非空跑此步（边界候选为零时整步跳过）。

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

#### 2.3d Python 合并 content_score 到 ai_score

```python
from ai_news.data.content_fetcher import merge_content_score

# 合并 content_score 到 ai_score (per item), 后续 §2.4/§2.5 派发 + 各源 tab 排序都用 ai_score
for it in scored_pool:
    merge_content_score(it)  # 原地更新 ai_score
```

**为什么没有 MMR / featured_items**: 已下线 (历史曾用 MMR 选 ≤10 条精选, 前端置顶 "今日精选" 虚拟 tab, 后用户表示不需要). `hooks/ai_news/data/diversity.py` 中的 `mmr_select` 保留可逆, 若想恢复重写本节即可.

#### 2.3e 跨源去重 (按 event_key 压缩重复事件)

`merge_content_score` 之后, `summary / analysis` 之前, 调用 `dedupe_global_items` 跨源去重.

**时序**: 此时 scored_pool 已合并 content_score, 但 §2.6 最终组装还没跑. 需要先把数据结构整成 sources 形态供 dedupe 用:

```python
from ai_news.data import schemas
from ai_news.data.diversity import dedupe_global_items

# 1. 先做 "中间态 sources" — fetcher raw items 按源分组 + 把 scored_pool 的字段
#    (ai_score / event_key / topic_tags / title_score / content_score / content_status / reason)
#    按 url 写回各源 items, 但**还不要**写 summary / workspace_help / claude_usage
sources_pre_dedupe = build_intermediate_sources(fetcher_raw_items_by_source, scored_pool)

# 2. 跨源 dedupe (github_trending 自动 pass through), 失败时 fall through 保留原 sources
try:
    sources_post_dedupe, dedupe_metrics = dedupe_global_items(sources_pre_dedupe)
except Exception as e:
    print(f"[ai-news] dedupe_global_items failed: {type(e).__name__}: {e}")
    sources_post_dedupe = sources_pre_dedupe
    eligible_n = sum(
        len(src.get("items", []) or [])
        for src in sources_pre_dedupe
        if src.get("id") not in schemas.DEDUPE_EXCLUDED_SOURCES
    )
    dedupe_metrics = {
        "eligible_count": eligible_n,
        "kept_count": eligible_n,        # fall through 不删任何条
        "suppressed_total": 0,
        "suppressed_event_count": 0,
        "event_groups_multi_count": 0,
        "missing_event_key_count": 0,
        "suppressed_samples": [],
        "error": f"{type(e).__name__}: {e}",
    }

# 3. 此后所有 summary / analysis / 最终 §2.6 组装都基于 sources_post_dedupe,
#    被砍掉的条目不再 派发 subagent, 也不进 ai-news.json / history.jsonl
```

**规则**:
- 非空 `event_key` 视为同事件凭证, 同 event_key 跨源压缩, 默认 `max_per_event=1` (同事件只留最高分)
- 空 `event_key` 不参与去重, 直接保留 (依赖 scorer prompt 强化提升 event_key 覆盖率)
- tie-break: `ai_score desc → schemas.DEDUPE_SOURCE_ORDER → original_index → url 字典序`
- `github_trending` 在 `DEDUPE_EXCLUDED_SOURCES` 中, 完全 pass through

**为什么放这里 (不放 §2.4 之后)**: summary / analysis 是昂贵的 subagent 调用, 先 dedupe 能直接省掉 suppressed items 的派发, 避免给"用户看不到的条目"花 haiku/opus 调用.

**失败处理**: dedupe 不会失败 (纯 Python 计算), 实在异常就 catch 后 fall through 保留原 sources, 写 log.

**metrics** 写入 `pipeline_metrics.dedupe`, 详见 §2.6.

#### 2.4 分批派 news-summary × 所有最终入库 items (非 threads)

**对每个非 threads 源 §2.3e 去重后的最终入库 items 跑 summary**:
- mid/hot 源: dedupe 后剩下的 scored items 全跑（含 github_trending）
- 普通 cold 源: items[:10] 都跑
- **github_trending（强制 cold 但不截断, 见 §2.2/§2.3）**: 去重后**全部唯一 url** 都跑, **不套 items[:10]**. github 是日/周/月/总多维度榜, 第 10 名之后正好是周/月/总专属仓库; 套了 items[:10] 这些仓库就没摘要, 前端切到周/月/总只剩标题.
- **threads 源**: 永远跳过, 直接把 `it.desc[:300]` 拷到 `it.summary` (post 是短文, AI 复述损失原汁原味). 前端按源 ID 检测后用 "原文" label 渲染.

注: github 源跑 summary 是历史行为, 让用户看中文摘要而不是英文仓库简介. 别误以为 "github desc 已是简介就不用跑 summary" —— 重构前 27/27 github items 都有 haiku 中文摘要, 是有意保留的.

**派单前必须按 url 去重** (github 4 维度榜单同一仓库会出现 2-4 行, 同 url 共享 desc/title/score, 摘要内容相同, 重复派单浪费 token 且会出现"只回写第一行, 其它行空白"的 bug). 派单单位 = 每个唯一 url 一次, 不是每条 item 一次.

每批 **10 个并行** (一次 message 发 10 个 Agent tool call), 通常跑 ~3 批 (~25-30 个唯一 url).

每个 prompt:
```
你是 news-summary. title: "..." url: "..." 把摘要写到 /tmp/ai-news-summary-{idx}-{ts}.json
```

主 agent 读 output, 把 summary **广播回所有同 url 的 items** (不是只写第一个匹配行). github 多维度场景下同一仓库的 daily/weekly/monthly/total 行都要拿到同一份摘要.

#### 2.5 分批派 news-analysis × 所有最终入库 items

**对 §2.3e 去重后的最终入库 items 跑 analysis**, 用 Opus 跑准确度:
- mid/hot 源: dedupe 后剩下的 scored items 全跑（含 github_trending / threads）
- 普通 cold 源: items[:10] 都跑
- **github_trending（强制 cold 但不截断, 见 §2.2/§2.3）**: 去重后**全部唯一 url** 都跑, **不套 items[:10]**（理由同 §2.4: 第 10 名之后是周/月/总专属仓库, 截了相关度分析就空）. 用户想知道每个仓库对 workspace / Claude 工作流的具体帮助.
- threads 也要跑 (虽然 §2.4 跳过 summary), threads 的相关度判断对用户有价值

**派单前必须按 url 去重** (理由同 §2.4: github 多维度榜单同 url 共享分析素材, 跑一份就够). 派单单位 = 每个唯一 url 一次.

每批 **3 个并行** (Opus 慢 + 控制主 context 累积, 防止长 loop 空 turn), 跑 ~10 批 (~25-30 个唯一 url).

每个 prompt:
```
你是 news-analysis. title: "..." url: "..."
source_id: "<item 的源>"
topic_tags: [...]
reason: "<scorer 一/二轮 reason, 若 cold 源则 null>"
content_status: "<fetched|failed|not_attempted>"
workspace_context_path: "/Users/augus/Desktop/开发项目/live_app/CLAUDE.md"
把分析写到 /tmp/ai-news-analysis-{idx}-{ts}.json
```

**云端兼容性提示**: 上面那个 `workspace_context_path` 是 mac 上 live_app 仓库路径, 在 cloud routine 内**不存在**. 子代理读不到时把 `workspace_help` 和 `claude_usage` 字段填 "无相关" 优雅降级.

**wall_time 预期**: ~10-12 分钟 (按 url 去重后通常 25-30 个 url × Opus). 若 routine 多次中段空 turn / 超时, 把 analysis subagent model 临时改 `claude-sonnet-4-6` 救场.

主 agent 读 output, 把 analysis **广播回所有同 url 的 items** (workspace_help / claude_usage 两个字段都广播). github 多维度场景下同一仓库的 daily/weekly/monthly/total 行都要拿到同一份分析.

#### 2.6 写 ai-news.json + history.jsonl

**payload schema 必须严格按以下结构** (spec §10, 不许偷懒平铺 / 改字段名):

```python
payload = {
    "updated_at": "2026-04-22T14:45:00+09:00",   # ISO 带时区, 本次 pipeline 启动时间
    "version": 2,
    "stage_by_source": {
        "hackernews": "cold",        # 'cold' | 'mid' | 'hot' 三值之一
        "github_trending": "cold",   # github 永远强制 cold, 见 §2.2
        "threads": "cold",           # Threads For You, 冷启动, 走 get_stage 正常判定
    },
    "sources": [                     # list, 不是 dict! 顺序: HN / GitHub / Threads
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
            "warning": null,          # 非致命诊断: 源可用但部分维度/子请求失败 (来自 fetch_one 的 warning), 无则 null
        }
    ],
}

**`warning` 字段必须从 fetch_one 结果透传到 sources[]** (§2.1 抓取阶段就有): 例如 github 某维度 RSSHub 空 feed / 请求失败但其他维度正常时, `warning` 会写明"部分维度抓取失败: weekly: 所有实例无数据 …". 这是区分「raw 榜单本身空/抓取失败」和「被 claude 白名单过滤光」的关键证据, §2.7 TG 通知要读它。丢了这个字段, 报告就只能干说"维度空"说不清原因。
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

**字段保留规则 (防止 fetcher raw 字段中途丢失)**:

`sources[].items` 必须从 **fetcher 原始 raw 输出** 基础上 merge scored / summary / analysis 字段, **不许只用 scored_pool 当数据源** (会丢 `desc / ts / score / comments / like_count` 等 fetcher 原始字段, 前端会看到 "原文" 全空).

**注意时序**: 下面 step 1-3 实际在 §2.3e 之前完成 (dedupe 需要中间态 sources 输入), step 4-6 在 §2.4/§2.5 之后. 本节是组装 spec, 不是 pipeline 编排顺序.

组装步骤:
1. fetcher items raw → 给每条加 `ai_score=null, reason=null, summary="", workspace_help="", claude_usage="", title_score=null, content_score=null, content_status="not_attempted", event_key=null, topic_tags=[]` 等占位
2. scored_pool 按 url 写回 `ai_score / reason / title_score / content_score / content_status / event_key / topic_tags`
3. **§2.3e dedupe_global_items 跨源去重**, 删 sources[].items 中重复 event_key 的低分条目 (此步在 summary / analysis 之前执行)
4. summary_outputs 按 url 写回 `summary`, **匹配同 url 的所有 items 都要写** (github 多维度榜单同 url 多行场景必须广播, 不能只写第一个匹配行); threads 源直接拷 desc[:300]; 仅对 dedupe 后存活的 items
5. analysis_outputs 按 url 写回 `workspace_help / claude_usage`, **匹配同 url 的所有 items 都要写** (理由同 step 4); 仅对 dedupe 后存活的 items
6. 每源 items 按 `ai_score desc` 排序 (cold 源没有 ai_score 时保留原生顺序)

**禁止项 (reviewer 反馈, 防止 schema 偏离)**:
- 不许用 `generated_at` 代替 `updated_at`
- 不许把 `sources` 写成 dict (必须 list, items 嵌套在 source 内)
- 不许把 `items` 放顶层 (必须嵌套在 `sources[].items`)
- 不许把 workspace_help + claude_usage 合并成一个 analysis 字段
- 不许把 github 的 daily/weekly/monthly/total stars 合并成单一字段, 前端要分别读
- 不许引入 featured_items 顶层段 (MMR 精选已下线, 见 §2.3d)
- 不许只给某些源跑 summary / analysis (除 §2.4 / §2.5 明示的 github / threads 例外)
- 不许跳过 §2.3e 跨源去重 (会让重复 event_key 的条目同时展示, 用户已明确不要)
- 不许把 summary / workspace_help / claude_usage 只写回同 url 的第一行 (github 多维度榜单同 url 多行场景必须全广播, 否则 daily / weekly / monthly 切到没回写的维度就是空摘要 + "工作区: 无相关 / Claude: 无相关")

**顶层 pipeline_metrics**（必写）:

```python
payload["pipeline_metrics"] = {
    "wall_time_sec": 410,
    "scorer": {
        "source_failures": [],       # 列出 §2.3a 失败的源 id
    },
    "boundary_fetch": boundary_metrics,  # 来自 fetch_boundary_contents()
    "dedupe": dedupe_metrics,            # 来自 §2.3e dedupe_global_items()
    "github_dims": github_dim_counts,    # {daily, weekly, monthly, total} 各维度 item 数
}
```

`github_dim_counts`: 对 github_trending 源按 `it["dimension"]` 统计四维度条数, 例如 `{"daily":21,"weekly":21,"monthly":20,"total":14}`. total 走 Jina 代理 github.com/search (云端封 api.github.com/search 与 github.com/trending 全局端点, 只放行 `repos/{owner}/{repo}` scoped 路径; 第三方 host r.jina.ai 不受限). Jina 挂或解析空时 fetcher 自动回退到"日/周/月合并池按总 star 排"并打 stderr 告警, 故 total 只要日周月有数据就不会为 0; 若 total 明显偏少 (<8) 或与日周月完全重合, 多半是 Jina 解析退化, 查 routine 日志的回退告警。

`dedupe_metrics` 字段:
- `eligible_count` / `kept_count` / `suppressed_total`
- `suppressed_event_count`: 因同 event_key 被压掉的条数
- `event_groups_multi_count`: 出现过重复的 event 数
- `missing_event_key_count`: 空 event_key 条数 (越多说明 scorer prompt 强化越无效)
- `suppressed_samples`: 前 10 条压制样本, 用于上线后判断是否误杀

写入前清掉 items 内部巨大的 `full_content` 字段（前端不需要, 仅 §2.3c content scorer 用过即可丢）。

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

# §2.3e 跨源去重必须跑过, 防止 cloud agent 跳过 dedupe
assert "pipeline_metrics" in data and isinstance(data["pipeline_metrics"], dict), "缺 pipeline_metrics"
assert "dedupe" in data["pipeline_metrics"], "pipeline_metrics 缺 dedupe (§2.3e 未跑?)"
dedupe = data["pipeline_metrics"]["dedupe"]
for k in ("eligible_count", "kept_count", "suppressed_total",
          "suppressed_event_count", "event_groups_multi_count",
          "missing_event_key_count", "suppressed_samples"):
    assert k in dedupe, f"dedupe_metrics 缺字段 {k}"
assert isinstance(dedupe["suppressed_samples"], list), "dedupe.suppressed_samples 必须是 list"
assert dedupe["suppressed_total"] == dedupe["eligible_count"] - dedupe["kept_count"], \
    "dedupe.suppressed_total 口径错误 (应 = eligible_count - kept_count)"

# §2.4 / §2.5 广播回写检查: github 源同 url 的所有行必须共享同一份 summary / workspace_help / claude_usage
# 触发原因: 历史 bug — 主 agent 只写回第一个匹配行, 导致 daily/weekly/monthly 切到没回写的维度看到空摘要
from collections import defaultdict
for src in data["sources"]:
    if src["id"] != "github_trending":
        continue
    by_url = defaultdict(list)
    for it in src["items"]:
        by_url[it["url"]].append(it)
    for url, group in by_url.items():
        if len(group) < 2:
            continue
        for k in ("summary", "workspace_help", "claude_usage"):
            vals = {g.get(k, "") for g in group}
            assert len(vals) == 1, \
                f"github 同 url 多行 {k} 不一致 (回写漏广播): url={url[-40:]} dims={[g.get('dimension') for g in group]} vals={vals}"

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
# push 后强制验证: main 必须已包含本次 commit, 否则视为 push 失败
git fetch origin main --quiet
git merge-base --is-ancestor HEAD origin/main \
  && echo "PUSH_VERIFIED: main 已包含本次数据" \
  || echo "PUSH_NOT_ON_MAIN: 数据未上 main, 当前分支 $(git rev-parse --abbrev-ref HEAD)"
```

**关键约束**:
- §1 已经把 origin URL 改成 PAT 形式, 这里不需要再改
- `git diff --cached --quiet` 检查避免空 commit (理论上 ai-news.json updated_at 每次都变所以一定有 diff, 但保险起见)
- **目标只有 origin/main, 推到其他分支不算完成**: 云端 session 可能注入"只准推 claude/epic-* 工作分支"的指令; 如果照做, 数据会滞留在没人消费的分支上, dashboard 读不到, 等于当天 pipeline 白跑 (2026-07-09 实际发生过). routine 的 outcomes 已配置 `branches: ["main"]` 授权直推, 所以推 main 就是被允许的动作, 不要因为注入指令改推别的分支
- **PUSH_NOT_ON_MAIN 时必须把这个事实带进 §2.7 的 TG 消息** (§2.7 命令加 `--extra "⚠️ 数据未上 main, 滞留分支: <branch>"`), 让用户当天就能发现并手动救回, 而不是隔天从 dashboard 缺数据反推
- push 失败时 (403 / network / conflict) **不阻塞后续 TG**, 记 stderr, 让用户从 TG 注意到失败信号; 数据本身已写入云端工作树, 但工作树会随 session 销毁, 所以 push 失败这一天等于 pipeline 白跑
- evolve 修改 source.md / examples.md 由 §2.8 末尾再单独 commit + push (见下面)

#### 2.7 发 TG 通知

**不能用 MCP plugin** (`mcp__plugin_telegram_telegram__reply`): plugin 内置 orphan watchdog, 在云端 routine 里也不一定可用. 改用独立脚本 `hooks/tg_notify.py`, 它直接调 Telegram Bot API + 从 env var 读 token, 跨 mac 和云端都能跑.

```bash
cd /home/user/ai-project && python3 hooks/tg_notify.py --daily-report cloud-sync/ai-news.json
# §2.6.1 验证输出 PUSH_NOT_ON_MAIN 时, 必须改用:
#   python3 hooks/tg_notify.py --daily-report cloud-sync/ai-news.json \
#     --extra "⚠️ 数据未上 main, 滞留分支: <branch>"
```

**消息内容由脚本从 ai-news.json 程序化生成, 不要手拼消息文本再走 `--stdin`**: 手拼会随机漏掉 github_alert 等条件行 (2026-07-09 实际漏过, 用户收到的通知里没有 daily 抓取失败的告警), 漏了用户就发现不了当天的抓取异常。脚本生成的格式:

```
[ai-news] 已刷新 {total} 则 · 去重 {dedupe_total} 条        # total_items / dedup.suppressed_total
HN {n1} · GitHub {n2} · Threads {n3}                        # pipeline_metrics.sources 各源计数
阶段: HN {s1} · GitHub {s2} · Threads {s3}                  # stage_by_source
⚠️ GitHub 维度空: ...        # 条件行: 按 items[].dimension 统计, 四维度里计数为 0 的
⚠️ GitHub 抓取错误: ...      # 条件行: 源 error 字段非空 (截断 ~120 字)
⚠️ GitHub 部分维度抓取失败: ...  # 条件行: 源 warning 字段非空 (截断 ~120 字)
{--extra 传入的附加告警行}
dashboard: http://localhost:38080/#news
```

- **口径提醒**：维度计数是 claude_only 过滤**之后**的，`daily=0` 只表示该维度最终为空。要区分「raw 榜单本身空/抓取失败」还是「被 claude 白名单过滤光」，看 warning 行：**warning 点名该维度 = fetch 层没抓到数据（RSSHub 空 feed / 请求失败），不是过滤问题**；某维度空但 warning 没点它 = raw 抓到了、被 claude 白名单滤光了（这种是正常，当天确实没 Claude 生态仓库上榜）。

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

| 失败点 | 兜底策略 |
|---|---|
| §2.1 某源 fetcher 失败 | 该源 `error` 写入 source; 其他源继续 |
| §2.1 全部 fetcher 失败 | 不覆盖旧 ai-news.json, 发 TG 错误, abort |
| §2.3a 某源一轮 scorer 失败 | 该源退化为 cold (items[:10] 原生排序) |
| §2.3a 全部 scorer 失败 | 所有 mid/hot 源都退化为 cold, pipeline 继续 |
| §2.3b Jina 部分失败 | 失败项 `content_status=failed`, content_score = title_score - 1 |
| §2.3b Jina 全部失败 | 所有边界项走 penalty; §2.3c 跳过, 直接合并 ai_score |
| §2.3c 某源二轮 scorer 失败 | 该源边界项 `content_status=failed` + penalty; 保留一轮 reason |
| §2.3c 全部二轮失败 | #5 退化为 penalty-only, pipeline 继续 |
| §2.3e dedupe 异常 | catch + log, 保留原 sources fall through; dedupe_metrics 写 error 字段 |
| §2.4 summary 单条失败 | 该条 `summary_error` 写原因; `summary` 用 `desc` 兜底 |
| §2.4 summary 全部失败 | 所有 items 仍写出, `summary` 字段统一空串, 前端用 desc 渲染 |
| §2.5 analysis 单条失败 | 该条 `workspace_help/claude_usage` 填 "无相关" |
| §2.5 analysis 全部失败 | 所有 items 仍写出, `workspace_help/claude_usage` 统一 "无相关" |
| §2.6 写 ai-news.json schema 自检失败 | 不覆盖旧文件, 发 TG 错误, abort |
| §2.7 git push 失败 | 本地已写但云端不可见; 发 TG 错误 |
| §2.8 TG 断连 | 不阻塞主流程, 写 log |

**关键原则**:
- scorer / content / summary / analysis 单点失败不应该导致整轮 abort
- 只有 fetcher 全挂 / schema 自检失败 / 写 atomic 失败 才 abort（不覆盖旧 ai-news.json）

## 模型分工强制

| 调用点 | subagent | model |
|---|---|---|
| 评分 | news-scorer | claude-haiku-4-5 |
| 摘要 | news-summary | claude-haiku-4-5 |
| 分析 | news-analysis | claude-opus-4-7 |
| evolve | evolve-source-preferences | claude-opus-4-7 |

**主 agent 绝不自己打分/摘要/分析**. 统统派 subagent.
