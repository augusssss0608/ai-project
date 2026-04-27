---
name: ai-news-fetch
description: AI 大事每日自动抓取 + 评分 + 摘要 + 分析 + 写入 + TG 通知. /loop 每次唤醒调用.
---

# AI 大事 v2 主编排

## 适用场景

**Only** 通过 `/loop` 动态模式调用. 每次唤醒都执行 `on_wakeup` 流程.

## on_wakeup 流程

### 步骤 1: 判断是否到 10:00 窗口 (含 sentinel 强制触发)

```python
import os
SENTINEL = "/tmp/ai-news-force-run"
now = datetime.now(LOCAL_TZ)

if os.path.exists(SENTINEL):
    os.unlink(SENTINEL)        # 自动失效, 不留后遗症
    run_full_pipeline()
    # 下次按正常 10:00 调度
    if now.hour < 10:
        target = datetime.combine(now.date(), time(10, 0), tzinfo=LOCAL_TZ)
    else:
        target = datetime.combine(now.date() + timedelta(days=1), time(10, 0), tzinfo=LOCAL_TZ)
elif now.hour == 10 and now.minute < 30:
    # 命中窗口, 跑完整 pipeline
    run_full_pipeline()
    # 下次目标: 明天 10:00
    target = datetime.combine(now.date() + timedelta(days=1), time(10, 0), tzinfo=LOCAL_TZ)
else:
    # 未命中, 算距下一个 10:00
    if now.hour < 10:
        target = datetime.combine(now.date(), time(10, 0), tzinfo=LOCAL_TZ)
    else:
        target = datetime.combine(now.date() + timedelta(days=1), time(10, 0), tzinfo=LOCAL_TZ)

    # 发 TG 通知: 告知当前时间与下次触发时间
    hours_left = (target - now).total_seconds() / 3600
    tg_msg = f"[ai-news] 时间检查 {now.strftime('%m/%d %H:%M')} JST\n未到窗口, 距下次 10:00 约 {hours_left:.1f}h"
    subprocess.run(["python3", "/Users/augus/Desktop/ai-project/hooks/tg_notify.py", "--stdin"],
                   input=tg_msg, text=True, capture_output=True)

delta = (target - now).total_seconds()
ScheduleWakeup(delaySeconds=min(3600, max(60, int(delta))))
```

本地时区: Asia/Tokyo (JST, UTC+9).

### 步骤 2: run_full_pipeline 编排

#### 2.1 抓取层 + hard_filter + 源特定过滤 + URL 去重 (subprocess Python, 不用 AI)

**过滤顺序**: 抓取 → 源特定 filter (threads 走 `threads_loose_filter`, 其他源走 `hard_filter`) → 白名单 filter (github_trending 多一道 `claude_only_filter`) → dedup_filter (剔除 history.jsonl 已出现过的 URL, **github_trending 源跳过**).

dedup_filter 在所有 stage 之前就生效 (cold/mid/hot 都会去重), 用户 down 过的 URL 和已展示无反馈的 URL 都被剔除.

**github_trending 特殊规则**:
1. 只保留明确跟 Claude 生态相关的仓库 (Claude / Anthropic / MCP / claude-code / agent skill 等), 因为 GitHub 热榜 AI 内容太杂, 用户只关心 Claude 相关.
2. **不走 dedup_filter**. 仓库是存续实体, 每次上榜可能带着新的 star 增量 (日/周/月维度), 允许反复展示. history.jsonl 仍会 append github 条目以供 scorer 的隐式负例分析使用, 但不用于去重.

```bash
python3 -c "
import sys, json
sys.path.insert(0, '/Users/augus/Desktop/ai-project/hooks')
from ai_news.data.fetchers import fetch_one
from ai_news.data.filters import apply_hard_filter, apply_dedup_filter, apply_claude_only_filter, apply_threads_loose_filter
from ai_news.data.history import load_all_urls
from pathlib import Path
import yaml

SOURCES = ['hackernews', 'github_trending', 'simonw', 'threads']
BASE = Path('/Users/augus/Desktop/ai-project/.claude/skills/ai-news-filter/sources')
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

#### 2.3 并行派 4 个 news-scorer (仅 mid / hot 源)

**Cold 源跳过 scorer**, 直接 items[:10] 作为 Top N (按原生排序).

**github_trending 源永远按 cold 行为处理, 但不截 items[:10]**: github 是多维度榜单 (日/周/月/总), 每条 item 带 `dimension` 字段, filter 后的全部 items 都要保留 (今天约 27 条, 4 维度合计), 否则前端切到 "总" 维度会看到空. 另外 scorer 对 github 的"按 star 真实 top"语义没意义 (scorer 只会打一个主观 AI score 反而破坏排序), 所以无论反馈多少也不走 scorer.

具体: 组装 Top N 时, github 源的 items 保留 filter_stats 里 after_dedup (== filter 后全部), 不做截断; 其他源按原逻辑 (cold → items[:10], mid/hot → scorer top N).

对每个 mid/hot 源:
1. Write `/tmp/ai-news-scorer-{sid}-{ts}.json`, 内容 JSON:
   ```json
   {
     "source_id": "hackernews",
     "stage": "mid",
     "source_md": "<sources/hackernews/source.md 完整内容>",
     "examples_md": "<build_examples_inline() 输出>",
     "candidates": [...]
   }
   ```
2. 在**一次 message 内**用 `Agent` tool 并行发 N 次 (N = mid/hot 源数量):
   - `subagent_type: news-scorer`
   - `model: claude-haiku-4-5`
   - `prompt: "你是 news-scorer. 读 /tmp/ai-news-scorer-{sid}-{ts}.json, 打分后写 /tmp/ai-news-scored-{sid}-{ts}.json"`
3. 主 agent 等所有 scorer 返回, 读每个 output 文件, 合并得 40 条以下 Top N.

#### 2.4 分批派 news-summary × N (每条 Top N 一次)

每批 **10 个并行** (一次 message 发 10 个 Agent tool call), 跑 ~4 批.

每个 prompt:
```
你是 news-summary. title: "..." url: "..." 把摘要写到 /tmp/ai-news-summary-{sid}-{idx}-{ts}.json
```

主 agent 每批后读 output 文件, 把 summary 合并回主列表 (仍在 context 中).

**threads 源例外**: threads 的 post 本身就是短文, AI 复述只会损失原汁原味, 所以不派 news-summary 子代理. 组装 payload 时直接把 `it.desc` (fetcher 返回的原贴文, 已截到 300 字符) 拷到 `it.summary` 字段, 让 schema 自检照常通过. 前端 (app.js) 看到 threads 源时会把这段当原文渲染 (label 显示 "原文" 而非 "摘要", 超 150 字符截断加省略号防破容器). 这样可以省下每天 ~5 次 haiku 调用, 同时让用户读到原话.

#### 2.5 分批派 news-analysis × N (每条 Top N 一次)

每批 **5 个并行** (Opus 慢, 更低并发). 跑 ~8 批.

每个 prompt:
```
你是 news-analysis. title: "..." url: "..." workspace_context_path: "/Users/augus/Desktop/开发项目/live_app/CLAUDE.md"
把分析写到 /tmp/ai-news-analysis-{sid}-{idx}-{ts}.json
```

主 agent 每批后读 output, 合并回主列表.

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
                    "reason": null,            # scorer 给的中文理由, cold 阶段 null
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
data = json.load(open("/Users/augus/Desktop/ai-project/data/ai-news.json"))
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
自检失败就不要发 TG, 写 log 后停止 pipeline (不覆盖旧 ai-news.json 已由 write_atomic 保证).

#### 2.7 发 TG 通知

**不能用 MCP plugin** (`mcp__plugin_telegram_telegram__reply`): plugin 内置 orphan watchdog, session 挂久了会自杀断连, 导致 /loop 挂机等 10:00 时 TG 工具不可用. 改用独立脚本 `hooks/tg_notify.py`, 它直接调 Telegram Bot API, 不依赖 MCP session 生命周期.

```bash
python3 /Users/augus/Desktop/ai-project/hooks/tg_notify.py --stdin <<EOF
[ai-news] 已刷新 {total} 则
HN {n1} · GitHub {n2} · Simon {n3} · Threads {n4}
阶段: HN {s1} · GitHub {s2} · Simon {s3} · Threads {s4}
dashboard: http://localhost:38080/#news
EOF
```

脚本失败时退出码非 0, 打印错误到 stderr (不含 token). 失败 graceful skip (写 log 不阻塞).

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

#### 2.9 清理临时文件

```bash
rm -f /tmp/ai-news-scorer-*-{ts}.json /tmp/ai-news-scored-*-{ts}.json \
      /tmp/ai-news-summary-*-{ts}.json /tmp/ai-news-analysis-*-{ts}.json \
      /tmp/ai-news-evolve-*-{ts}.json /tmp/ai-news-raw.json
```

## 错误降级

见 spec §14 表. 要点:
- 某源抓取失败: 其他源继续, 该源 `error` 带错
- 某源 scorer 失败: 该源退化成 cold 行为 (原生排序 Top N)
- 单条 summary/analysis 失败: 该条对应字段空
- TG 断连: 不阻塞主流程
- 整体失败: **不覆盖旧 ai-news.json**

## 模型分工强制

| 调用点 | subagent | model |
|---|---|---|
| 评分 | news-scorer | claude-haiku-4-5 |
| 摘要 | news-summary | claude-haiku-4-5 |
| 分析 | news-analysis | claude-opus-4-7 |
| evolve | evolve-source-preferences | claude-opus-4-7 |

**主 agent 绝不自己打分/摘要/分析**. 统统派 subagent.
