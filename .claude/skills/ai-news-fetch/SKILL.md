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

delta = (target - now).total_seconds()
ScheduleWakeup(delaySeconds=min(3600, max(60, int(delta))))
```

本地时区: Asia/Tokyo (JST, UTC+9).

### 步骤 2: run_full_pipeline 编排

#### 2.1 抓取层 (subprocess Python, 不用 AI)

```bash
python3 -c "
import sys, json
sys.path.insert(0, '/Users/augus/Desktop/ai-project/hooks')
from ai_news.fetchers import fetch_one
from ai_news.filters import apply_hard_filter
from pathlib import Path
import yaml

SOURCES = ['hackernews', 'github_trending', 'qbitai', 'ithome_tw']
BASE = Path('/Users/augus/Desktop/ai-project/.claude/skills/ai-news-filter/sources')
out = []
for sid in SOURCES:
    cfg = yaml.safe_load(open(BASE / sid / 'fetcher.yaml'))
    r = fetch_one(sid, cfg)
    if r.get('items'):
        r['items'] = apply_hard_filter(r['items'])
    out.append(r)
open('/tmp/ai-news-raw.json', 'w').write(json.dumps(out, ensure_ascii=False))
print(f'fetched: {[(s[\"id\"], len(s.get(\"items\", []))) for s in out]}')
"
```

读 `/tmp/ai-news-raw.json` 得到 4 源的候选列表.

#### 2.2 判定每源 stage

用 `ai_news.feedback.load_feedback()` + `get_stage(source_id, feedback)` 对每源得 `cold|mid|hot`.

#### 2.3 并行派 4 个 news-scorer (仅 mid / hot 源)

**Cold 源跳过 scorer**, 直接 items[:10] 作为 Top N (按原生排序).

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
        "github_trending": "cold",
        "qbitai": "cold",
        "ithome_tw": "cold",
    },
    "sources": [                     # list, 不是 dict! 顺序: HN / GitHub / 量子位 / iThome
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
                    "score": 484,              # HN points / GitHub stars, 无则 null
                    "comments": 276,           # HN 评论数, 无则 null
                    "ts": "2026-04-21T03:43:03Z",
                    "ai_score": null,          # cold 阶段 null, mid/hot 才有 0-10 分
                    "reason": null,            # scorer 给的中文理由, cold 阶段 null
                    "summary": "news-summary 的中文摘要, 硬上限 80 字 (前端超了截断加 …)",
                    "workspace_help": "news-analysis 给 workspace 的建议, 硬上限 40 字, 或 '无相关'",
                    "claude_usage": "news-analysis 给 Claude Code 使用的建议, 硬上限 40 字, 或 '无相关'",
                    "hn_url": "https://news.ycombinator.com/item?id=...",  # HN only, 其他源空串
                    "summary_error": "",       # 子代理失败时填 error 原因, 否则空串
                }
            ],
            "error": null,            # 该源抓取/pipeline 失败时填 error 字符串
        }
    ],
}
```

**禁止项 (reviewer 反馈, 防止 schema 偏离)**:
- 不许用 `generated_at` 代替 `updated_at`
- 不许把 `sources` 写成 dict (必须 list, items 嵌套在 source 内)
- 不许把 `items` 放顶层 (必须嵌套在 `sources[].items`)
- 不许把 workspace_help + claude_usage 合并成一个 analysis 字段

**组装后, 按以下顺序写入**:

```python
from ai_news.io import write_ai_news_atomic
from ai_news.history import append_items

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
print("schema 自检通过")
```
自检失败就不要发 TG, 写 log 后停止 pipeline (不覆盖旧 ai-news.json 已由 write_atomic 保证).

#### 2.7 发 TG 通知

用 `mcp__plugin_telegram_telegram__reply`:
```
[ai-news] 已刷新 {total} 则
HN {n1} · GitHub {n2} · 量子位 {n3} · iThome {n4}
阶段: HN {s1} · GitHub {s2} · 量子位 {s3} · iThome {s4}
dashboard: http://localhost:38080/#news
```

失败 graceful skip (写 log 不阻塞).

#### 2.8 Evolve 检查 (每源)

对每个 hot 源:
1. 读 source.md frontmatter `last_evolve_at`
2. 统计 `last_evolve_at` 之后该源新增反馈数
3. 若 >= 20:
   - `ai_news.evolve.load_frontmatter()` 读 `evolve_count` (= N)
   - `ai_news.evolve.backup_source(source_md_path, N)`
   - 组装 evolve 输入 JSON, Write 到 `/tmp/ai-news-evolve-{sid}-{ts}.json`
   - 派 evolve-source-preferences subagent (model: claude-opus-4-7)
   - 读 output, 记 `ai_news.evolve.write_evolve_log(entry)`
   - 发 TG 通知

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
