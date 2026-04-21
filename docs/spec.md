# AI 大事 v2 设计文档

- 日期: 2026-04-20
- 作者: augus
- 状态: 草案 (v4, 已合并第二轮 reviewer 反馈 + 用户决定删除兜底机制)
- 目标代码路径: `~/.claude/hooks/ai_news/*` + `~/.claude/skills/ai-news-*` + `~/.claude/agents/news-*`

---

## 1. 背景

### 1.1 v1 现状

现有 `~/.claude/hooks/fetch-ai-news.py` (534 行) 做四件事:

1. 从 4 个源抓取新闻: HackerNews (Algolia), GitHub Trending daily, 量子位 RSS, iThome (台湾) RSS
2. 硬编码正则黑白名单过滤 (`CORE_AI_RE` / `HARD_NOISE_RE` 等)
3. 每条过 Jina Reader 抓正文 → Haiku 生成 50-80 字摘要 → Opus 生成"工作区帮助 / Claude 使用"双维度分析
4. 输出 `~/.claude/usage-stats/ai-news.json` 供 dashboard 消费

Dashboard 有"每日 AI 大事" tab (`usage_web_render.py::_render_news_panel`), 含:
- 条目展示 + "有帮助" 投票按钮 (POST `/news/vote`, 写入 `ai-news-feedback.json`)
- "刷新" 按钮 (POST `/news/refresh`, 后端 subprocess 调 `fetch-ai-news.py`) — **v2 删除**

v1 的 source id 枚举 (已在前端 render 和 feedback 写入中使用):
`hackernews` / `github_trending` / `qbitai` / `ithome_tw` — v2 沿用, 不改名.

### 1.2 和新需求的差距

- 调度: v1 无, v2 每天 10am 自动
- 反馈闭环: v1 投票写文件但完全没接回过滤, v2 AI 基于反馈演化过滤标准
- 过滤逻辑: v1 硬编码正则, v2 硬规则 + LLM few-shot 评分, 每源可客制化
- 数量控制: v1 每源 15-20 条全上摘要, v2 每源 Top 10 (评分后) 再上摘要
- 每源策略: v1 写死在 fetch_*() 里的常量, v2 每源独立 `sources/<id>/` 目录

---

## 2. 目标 / 非目标

### 2.1 目标
1. `/loop` 常驻 tmux 会话, 每天 10am 自动跑完整流程
2. 反馈真正回到过滤循环, AI 学着你的口味筛 Top 10
3. 每源可客制化: 抓取策略 (fetcher.yaml) + 语义偏好 (source.md), 改一处不影响别源
4. 偏好文件 `source.md` 会跟着反馈演化 (evolve) 且有备份支持用户手动回滚
5. 复用现有稳定代码 (抓取函数 / `_call_claude` / dashboard 前端)

### 2.2 非目标 (v1 不做)
- Twitter / Threads 抓取 (rsshub 方案暂不稳定, 后续版本)
- Dashboard 大改版 (只加 `reason`/`stage` 显示 + 删除刷新按钮)
- 跨源去重 / A/B prompt / Opus 复核边界条目 (过度设计, 延后)
- 从 Codex 引入第二 AI 家 (v1 纯 Claude)
- 手动一键跑完整流程 (`/news/refresh` 删除, `fetch-ai-news.py` 降级为"抓取层 debug 入口")

---

## 3. 架构总览

```
[/loop 动态主 agent, Sonnet 4.6, 常驻 tmux]
       │
       │ 每次唤醒: delta = 下一个 10:00 - now
       │          ScheduleWakeup(delaySeconds = min(3600, delta))
       │ 到 10:00 命中 → 读 ai-news-fetch/SKILL.md 指令
       ▼
[Skill: ai-news-fetch (流程编排指令)]
       │ 主 agent 按指令依次执行:
       │
       ├─(subprocess)──> python -c "from ai_news.fetchers import fetch_all; ..."
       │   并行抓 4 源, 硬规则 HARD_NOISE_RE 过滤后得候选
       │   写到临时 pickle / json 给下一步用
       ▼
[派 4 个 scorer subagent (通用 news-scorer, Haiku 4.5) — 一批并行]
       │ 主 agent 用 dispatching-parallel-agents 一次 message 内发 4 个 Agent tool call
       │ 传参通过【临时文件 + prompt 路径引用】(见 §9.0)
       │ 每个 subagent 独立 context, Read 临时文件 → 评分 → 返回 Top ≤10 + ai_score + reason
       │ 主 agent 收到 4 个结果后立即写入临时 jsonl (/tmp/ai-news-scored.jsonl), 不全持于 context
       ▼
[分批派 summary subagent × ≤40 (news-summary, Haiku 4.5)]
       │ 分批并行: 每批 10 个, 共 ~4 批; 每批完结果落临时文件, 下一批再派
       │ 每条输出 50-80 字中文摘要
       ▼
[分批派 analysis subagent × ≤40 (news-analysis, Opus 4.7)]
       │ 分批并行: 每批 5 个, 共 ~8 批 (Opus 单条慢, 并发度更低)
       │ 每条输出 workspace_help / claude_usage 两维度
       ▼
[主 agent 从临时文件汇总 → 写 ai-news.json (原子 rename) + append history.jsonl]
       │
       ▼
[TG 通知: 通过 mcp__plugin_telegram_telegram__reply]
       │ "新闻已刷新 X 则, dashboard: http://..."
       │
       ▼
[evolve 检查: 按源扫描, 热启动源距上次 evolve 新增反馈 ≥ 20 →
         派 evolve-source-preferences subagent (Opus 4.7)]
       │ 备份 source.md → source.md.v{N}, 重写, 记 diff log
       │
       ▼
[回门岗: ScheduleWakeup 到下一整点 (最大 3600s), 循环]
```

**关键原则**:
- **主 agent 不做 AI 推理**: 所有需要思考的任务都派 subagent, 主 agent 只做"调函数、派 subagent、汇总、写文件"
- **subagent 模型强制**: 每个 subagent md 里 `model:` frontmatter 写死, 不可能跑到其他模型
- **subagent context 隔离**: 4 源 scorer 并行派, 互不串源
- **分批落盘**: 主 agent 不一次性持有所有 subagent 结果 (会撑爆 context), 每批结果写临时 jsonl, 最终一次性 load 写 ai-news.json
- **结构化数据通过临时文件**: subagent prompt 只传路径, 不嵌入大块 JSON (见 §9.0)

**耗时预估** (最坏情况):
- 抓取层 Python: ~15s (4 源并行 HTTP)
- Scorer (4 源并行, Haiku): ~30s (一批 4 个, 一次 message 发完)
- Summary (40 条, Haiku, 10 并发 × 4 批): ~3-4 min
- Analysis (40 条, Opus, 5 并发 × 8 批): ~6-10 min
- 汇总写文件 + TG: ~5s
- Evolve (如触发): +3-5 min
- **完整 pipeline ≈ 10-15 分钟**. tmux pane 会持续输出, 用户观察进度

---

## 4. 模型分工 (subagent 架构)

| 角色 | 模型 | 实体 | 每日调用 |
|---|---|---|---|
| /loop 主 agent (协调) | claude-sonnet-4-6 | Claude Code 会话启动时 `--model sonnet` | 24 次唤醒 (精确算法, 见 §5) |
| 评分 scorer | claude-haiku-4-5 | `~/.claude/agents/news-scorer.md` | 4 次派遣 (并行, 每源一次) |
| 摘要 summary | claude-haiku-4-5 | `~/.claude/agents/news-summary.md` | 40 次派遣 (每条一次, 并发 ≤10) |
| 分析 analysis | claude-opus-4-7 | `~/.claude/agents/news-analysis.md` | 40 次派遣 (每条一次, 并发 ≤5) |
| evolve | claude-opus-4-7 | `~/.claude/agents/evolve-source-preferences.md` | 0-4 次 (热启动源按阈值) |

**成本估算 (修正自两轮 reviewer 反馈)**:
- 主 agent 轻量唤醒: Sonnet 2k tokens × 每天 ~23 次 ≈ 46k tokens/天 ≈ **$0.14/天**
- 主 agent 完整编排那 1 次: Sonnet 30-50k tokens (要汇总 40 条结果 + 派遣所有 subagent) ≈ **$0.15-0.25**
- Scorer (4 次 × Haiku × 每次 6k tokens) ≈ $0.02
- Summary (40 次 × Haiku × 每次 3k tokens) ≈ $0.10
- Analysis (40 次 × Opus × 每次 4k tokens) ≈ $2.4
- Evolve (最多 4 次 × Opus × 每次 10k tokens) ≈ $0.75 (不是每天触发)
- **日常总计 ≈ $2.8/天**, 含 evolve 日 ≈ $3.5/天

---

## 5. /loop 精确时间算法

原方案"每 1h 唤醒比时间"错在启动点决定了每日命中点 (9:59 启动 → 永远 10:59 命中). 修正:

```python
# 伪代码, 实际写在 ai-news-fetch/SKILL.md 的指令里
def on_wakeup():
    now = datetime.now(tz=LOCAL_TZ)
    target = get_next_10am(now)          # 今天 10:00 或明天 10:00
    delta = (target - now).total_seconds()

    if delta <= 60:                       # 到 10:00 了 (容差 1 分钟)
        run_full_pipeline()
        target = get_next_10am(now + timedelta(minutes=5))  # 跳过刚跑过的这次
        delta = (target - now).total_seconds()

    ScheduleWakeup(delaySeconds=min(3600, int(delta)))
```

**行为验证**:
- 9:59:30 启动 → delta=30s < 60s → 跑 (但今天 10:00 还没到, 需要更严格判定)
- 实际需要 `if delta <= 60 and now.hour == 10`. 避免 9:59 起来就跑

更精确:
```python
if now.hour == 10 and now.minute < 30:    # 命中窗口: 10:00-10:30
    run_full_pipeline()
    # 下次目标: 明天 10:00
else:
    # 未命中: 计算距下一个 10:00
    target = next_10am_after(now)
    delta = (target - now).total_seconds()

ScheduleWakeup(delaySeconds=min(3600, int(delta)))
```

启动在任意时间都会最终命中 10:00 窗口, 不依赖启动点.

**数据更新时间**: Dashboard 显示的"数据更新时间"直接读 ai-news.json 的 `updated_at` 字段, 不需要单独的 heartbeat 文件.

---

## 6. 目录结构

### 6.1 Skills (编排指令 + 数据目录)

```
~/.claude/skills/
├── ai-news-fetch/
│   └── SKILL.md                      # /loop 主入口, 编排指令 (~100 行)
│
└── ai-news-filter/
    ├── sources/
    │   ├── hackernews/
    │   │   ├── source.md             # 语义偏好 (可被 evolve 重写)
    │   │   ├── fetcher.yaml          # 抓取参数
    │   │   └── examples.md           # 最近 N 条点赞/未点赞快照 (few-shot 数据)
    │   ├── github_trending/{source.md, fetcher.yaml, examples.md}
    │   ├── qbitai/{source.md, fetcher.yaml, examples.md}
    │   └── ithome_tw/{source.md, fetcher.yaml, examples.md}
    └── reference/
        ├── scoring-criteria.md       # 所有源共享的打分准则
        ├── feedback-evolution.md     # evolve 规则
        └── cold-start-strategy.md    # 冷/中/热启动退化
```

**注意**: `ai-news-filter/` 下**没有 SKILL.md**. 这是一个数据目录, 不是可触发的 skill. subagent md 里引用路径读文件.

### 6.2 Subagents

```
~/.claude/agents/
├── news-scorer.md                    # model: haiku-4-5, 通用评分员
├── news-summary.md                   # model: haiku-4-5, 通用摘要生成
├── news-analysis.md                  # model: opus-4-7, 通用双维度分析
└── evolve-source-preferences.md      # model: opus-4-7, 重写 source.md
```

**C1 定稿**: 每种任务一个通用 subagent, 主 agent 派遣时传 prompt 参数 (source_id 等). 4 源差异全在 `sources/<id>/source.md`, subagent md 不做源特化.

### 6.3 Python 模块

```
~/.claude/hooks/
├── ai_news/
│   ├── __init__.py
│   ├── fetchers.py           # 抓取: fetch_hn_algolia / fetch_github_trending / fetch_rss
│   ├── filters.py            # 硬规则: HARD_NOISE_RE 等 (沿用 v1 正则)
│   ├── feedback.py           # 反馈读写 + get_stage(source_id) + get_few_shot_examples()
│   ├── history.py            # ai-news-history.jsonl 写入 + 查询
│   ├── io.py                 # 读写 ai-news.json / source.md / examples.md (原子 rename)
│   └── evolve.py             # evolve 辅助: 备份 source.md.v{N} + 写 diff log
│
└── fetch-ai-news.py          # 降级为"抓取层 debug 入口"
                              # 只跑 fetchers + filters, 输出 /tmp/ai-news-raw-{source}.json
                              # 用于调 fetcher.yaml 参数时看原始抓取结果
                              # 不跑 scorer/summary/analysis
```

### 6.4 数据文件

```
~/.claude/usage-stats/
├── ai-news.json                      # 当前展示数据 (dashboard 消费)
├── ai-news-feedback.json             # 投票 (v1 格式不变)
├── ai-news-history.jsonl             # 新增: 每次跑完 append 所有展示过的 items (负例池)
├── ai-news-evolve-log.jsonl          # 新增: 每次 evolve 的 diff 记录
└── ai-news-pipeline.log              # 新增: 每次 pipeline 运行日志
```

---

## 7. 每源 source.md / fetcher.yaml / examples.md

### 7.1 source.md 模板

```markdown
---
source_id: hackernews
label: Hacker News
updated_by: cold_start | manual | evolve_v3
last_evolve_at: 2026-04-20T10:05:00+09:00
evolve_count: 0
---

# HN 评分偏好

## 核心判断维度
(人类初稿 / evolve 后由 AI 重写)
- HN 的价值在讨论热度 >= 单纯 score, 评论数 100+ 的优先
- 优先: 开源 agent/框架发布, MCP 类工具, 技术深度文章
- 次优: benchmark 对比, 技术综述
- 扣分: 已被硬规则漏过的融资/产业类

## 用户正例特征 (evolve 自动提取, 冷启动为空)
- 高频关键词: (evolve 填充)
- 偏好模式: (evolve 填充)

## 用户负例特征 (evolve 自动提取, 冷启动为空)
- 低频但曾出现: (evolve 填充)
- 被跳过模式: (evolve 填充)
```

### 7.2 fetcher.yaml (每源独立抓取参数)

```yaml
# sources/hackernews/fetcher.yaml
type: hn_algolia
params:
  query: "AI OR Claude OR Anthropic OR LLM OR MCP OR OpenAI OR Gemini OR DeepSeek"
  sort_by: points          # points | comments | created_at
  time_window_hours: 48
  min_points: 30
  limit: 20                # 评分前候选上限, 评分后 Top 10
```

```yaml
# sources/github_trending/fetcher.yaml
type: github_trending
params:
  since: daily             # daily | weekly | monthly
  limit: 20
```

```yaml
# sources/qbitai/fetcher.yaml
type: rss
params:
  url: https://www.qbitai.com/feed
  time_window_hours: 48
  limit: 15

# sources/ithome_tw/fetcher.yaml
type: rss
params:
  url: https://www.ithome.com.tw/rss
  time_window_hours: 48
  limit: 15
```

### 7.3 examples.md (few-shot 数据, 被 evolve 刷新)

```markdown
# 正例 (用户标记"有帮助", 按阶段截取最近 N 条)
- [2026-04-15] {title} — {url}
  desc: ...
- ...

# 负例 (history 中存在但未点赞, 且 ≥ 7 天)
- [2026-04-10] {title} — {url}
  desc: ...
- ...
```

**few-shot 数量按阶段调整** (reviewer 反馈 #14):
- 冷启动: 不用 few-shot
- 中启动: 正负各 10 条
- 热启动: 正负各 20-30 条

---

## 8. 三档启动 + evolve

### 8.1 启动阶段判定 (按源独立)

```python
# ai_news/feedback.py
def get_stage(source_id: str, feedback: dict) -> str:
    count = 0
    for v in feedback.get("votes", {}).values():
        vs = v.get("source", "")
        # 兼容: 历史 vote 可能 source 字段缺失或空字符串 (v1 早期版本).
        # 这种情况用 URL 反查 ai-news-history.jsonl 能获取源归属, 但查询成本高;
        # 简化处理: 空 source 视为未知, 不计入任何源统计 (保守, 避免错判).
        if vs == source_id:
            count += 1
    if count < 10:  return "cold"
    if count < 50:  return "mid"
    return "hot"
```

**source_id 枚举锁定**: v2 必须和 v1 前端 / 后端一致:
- `hackernews` (v1 `fetch_hackernews()` 返回)
- `github_trending` (v1 `fetch_github_trending()` 返回)
- `qbitai` (v1)
- `ithome_tw` (v1 `fetch_ithome()` 返回的是 `ithome_tw`, 沿用)

**实施时校对**:
- `usage_web_render.py::_render_news_item` 的 `data-vote-source` 是否用 `s["id"]` 正确传递
- `/news/vote` 后端是否正确接收并写入 `ai-news-feedback.json.votes.<url>.source`
- 若发现存量 feedback 有空 source, 写一次性迁移脚本回填 (从 history.jsonl 按 url 查 source)

### 8.2 各阶段行为

**冷启动 (< 10 条)**:
- 不派 scorer subagent
- 硬规则过滤后按源原生排序取 Top N (N = min(10, 实际过滤后数量))
  - HN: 按 `score` (HN points, int) desc
  - GitHub: 按 `today_stars_int` desc — **注意**: v1 `fetch_github_trending()` 返回的 `today_stars` 是 HTML 抓下来的字符串 (如 `"123 stars today"`), 字典序排会把 "9" 排在 "123" 前面. fetcher 重构时必须 `re.search(r'\d+', s).group()` 提取数字并转 int, 新字段叫 `today_stars_int`, 原 `today_stars` 字符串保留用于前端显示.
  - RSS: 按 `pubDate` (parsed datetime) desc
- 该源 `stage: "cold"` 写入 ai-news.json
- 目的: 反馈不足时不让 AI 瞎编

**中启动 (10-50 条)**:
- 派 scorer subagent, 传入: source.md + 10 正例 + 10 负例 + 候选列表
- Top N = min(10, 得分 >= 5 的数量), 平票按原生排序 tiebreak
- 该源 `stage: "mid"`

**中启动首次 examples.md 的初始化 (reviewer 反馈 #12)**:
- 中启动第一次跑时, `examples.md` 可能是冷启动期的初始空内容 (evolve 还没跑过)
- 主 agent 不依赖 `examples.md` 落盘版本, 而是**现场生成**:
  ```python
  # ai_news/feedback.py
  def build_examples_inline(source_id: str, feedback: dict, history: list, limit: int = 10) -> str:
      positives = get_positives(source_id, feedback, limit=limit)  # 从 feedback.votes 取
      negatives = get_negatives(source_id, feedback, history, limit=limit)  # 从 history 取
      return render_examples_md(positives, negatives)  # 按 §7.3 格式拼成字符串
  ```
- 拼成的字符串直接塞进 scorer subagent 输入 JSON 的 `examples_md` 字段 (不读文件)
- 热启动的 evolve 完成后, 才开始往 `examples.md` 文件落盘 (作为缓存 + 查看用途)

**热启动 (≥ 50 条)**:
- 同中启动的 scorer 行为, 但 few-shot 加到正负各 20-30 条
- **额外**: 跑完 pipeline 后检查 evolve 条件 (§8.3)
- 该源 `stage: "hot"`

### 8.3 Top N 是上限不是下限

硬规则过滤 + scorer 过滤后某源可能只有 4 条, 就展示 4 条. TG 通知动态显示实际数量:
```
[ai-news] 已刷新 31 则
HN 10 · GitHub 7 · 量子位 10 · iThome 4
```

### 8.4 evolve 机制

**触发条件** (只对热启动源):
- 距上次 evolve 该源新增反馈 ≥ 20 条

**流程**:
1. 主 agent 读当前 `sources/<id>/source.md`
2. 备份: `cp source.md source.md.v{evolve_count}` (evolve_count 从 frontmatter 读)
3. 派 evolve subagent (Opus), 输入:
   - 当前 source.md 整个文件
   - 该源所有正例 (最近 30 条点赞)
   - 该源所有负例 (history 里 ≥ 7 天未点赞, 最近 30 条)
4. Subagent 返回新 source.md 内容 (保留 frontmatter, 更新 evolve_count + last_evolve_at + updated_by=evolve_v{N+1})
5. 主 agent 原子 rename 写回
6. 记 diff 到 `ai-news-evolve-log.jsonl`

**手动回滚**:
- evolve 前生成的 `source.md.v{N-1}` 备份保留, 作为手动回滚用
- 若用户观察到某源 evolve 后推荐质量下降, 可手动执行:
  ```bash
  cp ~/.claude/skills/ai-news-filter/sources/<id>/source.md.v{N-1} \
     ~/.claude/skills/ai-news-filter/sources/<id>/source.md
  ```
- 备份文件长期保留, 不自动清理 (每次 evolve 产生一份, 60 天内都可回滚)
- **不做自动回滚**: v1 不实现"点赞率自动监控 + 回滚", 简化实施. 若未来观察到 evolve 经常改坏, 再加 (见 §19 后续扩展)

---

## 9. Subagent 契约

### 9.0 参数传递机制 (Blocker 修复)

Claude Code 的 Agent tool 只接受单一字符串 `prompt` 参数 + `subagent_type`, 不支持结构化参数. spec 所有 "prompt 参数: source_id, candidates JSON, source_md_path" 的描述实际上通过以下两种机制实现:

**机制 A — 路径引用 (主要方式)**:
- 主 agent 用 Write tool 把结构化数据写临时文件 `/tmp/ai-news-<role>-<source_id>-<ts>.json`
- 派 subagent 的 prompt 是**自然语言 + 路径**, 例如:
  ```
  你是 news-scorer. 请读 /tmp/ai-news-scorer-hackernews-20260420T1000.json
  (包含候选列表、source.md 内容、examples), 按 SKILL 指令打分,
  把结果写到 /tmp/ai-news-scored-hackernews-20260420T1000.json
  ```
- subagent 需要 `Read` + `Write` 权限操作临时文件
- 临时文件在 pipeline 结束时由主 agent 清理 (主 agent 自己 unlink)

**机制 B — Prompt 内联 (少量数据)**:
- 若数据很小 (单条 title+url, 约 300 字以内), 直接嵌 prompt 文本
- 例如 summary subagent 输入就是 `title` + `url`, 直接嵌入 prompt

**临时文件路径规范**:
```
/tmp/ai-news-scorer-{source_id}-{ts}.json        # 主 agent 写, scorer 读
/tmp/ai-news-scored-{source_id}-{ts}.json        # scorer 写, 主 agent 读
/tmp/ai-news-summary-{source_id}-{idx}-{ts}.json # 每条摘要各一, 并行隔离
/tmp/ai-news-analysis-{source_id}-{idx}-{ts}.json
/tmp/ai-news-evolve-{source_id}-{ts}.json
```

**tools 白名单规则**: Claude Code subagent md 的 `tools` 字段是白名单 (只启用列出的工具). 以下 4 个 subagent 的 tools 基于此机制推导.

### 9.1 news-scorer

```markdown
---
name: news-scorer
description: 对单源候选新闻打分, 输出 Top N + reason
model: claude-haiku-4-5
tools: Read, Write
---

# 评分员指令

主 agent 派遣你时 prompt 会给出 `input_path` 和 `output_path`.

input_path 对应的 JSON 结构:
```json
{
  "source_id": "hackernews",
  "stage": "cold" | "mid" | "hot",
  "source_md": "<source.md 内容完整字符串>",
  "examples_md": "<examples.md 内容, 可能是空字符串>",
  "candidates": [{"title":"...","url":"...","desc":"...","score":243,"comments":87,...}]
}
```

步骤:
1. Read input_path 获取所有输入
2. 若 `stage == "cold"`, 返回错误: 冷启动不应调用 scorer
3. 按 source_md 偏好 + examples few-shot, 对 candidates 每条给 0-10 分 + ≤ 25 字 reason
4. 按 ai_score desc 取前 N (N = min(10, score >= 5 的数量))
5. Write output_path 写 JSON: `{"source_id":"hackernews","items":[{"url","title","ai_score","reason"}, ...]}`
6. 返回一句话确认: "scored {N} items to {output_path}"

## 规则
- 候选少于 10 条返回实际数量, 不凑数
- reason 要具体, 不能只说"相关/不相关"
```

### 9.2 news-summary

```markdown
---
name: news-summary
description: 对新闻单条生成 50-80 字中文摘要
model: claude-haiku-4-5
tools: WebFetch, Write
---

# 摘要员指令

主 agent 派遣你时 prompt 给出 `title`, `url`, `output_path`.
(title/url 足够短, 直接嵌入 prompt; 摘要结果写 output_path)

步骤:
1. 用 WebFetch 抓 https://r.jina.ai/{url} 获取正文 (Jina Reader)
2. 生成 50-80 字中文摘要, 只写结论不铺垫, 不 markdown/引号/前后缀
3. Write output_path: `{"summary":"...","warning":""}`, 抓取失败时 `warning: "jina_failed"`, summary 仅凭 title 生成
4. 返回确认: "summary written to {output_path}"
```

### 9.3 news-analysis

```markdown
---
name: news-analysis
description: 分析新闻对当前工作区 + Claude 使用的帮助
model: claude-opus-4-7
tools: Read, WebFetch, Write
---

# 分析员指令

主 agent 派遣你时 prompt 给出 `title`, `url`, `workspace_context_path`, `output_path`.

步骤:
1. Read workspace_context_path (CLAUDE.md) 了解工作区架构
2. WebFetch 抓正文 (Jina Reader)
3. 生成两维度分析:
   - `workspace_help`: 一句话 30-60字, 或 "无相关"
   - `claude_usage`: 一句话 30-60字, 或 "无相关"
4. Write output_path: `{"workspace_help":"...","claude_usage":"...","warning":""}`
5. 返回确认

## 规则
- workspace_help 必须具体到工作区技术栈 (Flutter / Go Kratos / Lua), 不能泛泛
- claude_usage 关注 skill/plugin/prompt 技巧/模型能力/工作流改进
- 都无关就都写"无相关"
```

### 9.4 evolve-source-preferences

```markdown
---
name: evolve-source-preferences
description: 根据反馈数据重写单源 source.md 的偏好段落
model: claude-opus-4-7
tools: Read, Write
---

# 演化员指令

主 agent 派遣你时 prompt 给出 `input_path`, `output_path`.

input_path 对应 JSON:
```json
{
  "source_md_current": "<source.md 完整内容>",
  "source_md_path": "/Users/augus/.claude/skills/ai-news-filter/sources/<id>/source.md",
  "positives": [{"title":"...","url":"...","desc":"..."}, ...],  // 最近 30 条点赞
  "negatives": [...],                                              // 最近 30 条负例
  "evolve_count_new": 4,                                           // 本次是第几版
  "examples_md_path": "/.../examples.md"                           // evolve 同时刷新 examples
}
```

步骤:
1. Read input_path 获取所有输入
2. 分析 positives/negatives 共同特征
3. 重写三段: 「核心判断维度」(保留人类初稿意图 + 融合反馈) / 「用户正例特征」/ 「用户负例特征」
4. frontmatter 更新: evolve_count=new, last_evolve_at=now ISO, updated_by=evolve_v{new}
5. Write source_md_path: 写入整个新 source.md
6. Write examples_md_path: 按 §7.3 格式刷新 (正例 + 负例 最新数据)
7. Write output_path: `{"evolved":true,"evolve_count_new":4,"diff_summary":"..."}` (diff 摘要供 log)

## 规则
- 保留 frontmatter 所有其他字段
- 「核心判断维度」不能完全丢弃人类初稿意图, 在其基础上增强
- 不要加偏激判断 (如"只看开源"), 保持多样性
```

---

## 10. 输出 `ai-news.json` Schema

**字段名改动** (reviewer 反馈 #13): v2 的 AI 评分字段叫 `ai_score` (0-10), 保留 v1 的 `score` (HN points).

```json
{
  "updated_at": "2026-04-20T10:12:34+09:00",
  "version": 2,
  "stage_by_source": {
    "hackernews": "cold",
    "github_trending": "mid",
    "qbitai": "cold",
    "ithome_tw": "cold"
  },
  "sources": [
    {
      "id": "hackernews",
      "label": "Hacker News",
      "source_url": "https://news.ycombinator.com/",
      "updated_at": "2026-04-20T10:12:00+09:00",
      "stage": "cold",
      "items": [
        {
          "title": "...",
          "url": "...",
          "score": 243,                 // v1 保留: HN points
          "comments": 87,               // v1 保留
          "ts": "2026-04-20T03:00:00Z", // v1 保留
          "ai_score": 8,                // v2 新增: 0-10 评分, 冷启动为 null
          "reason": "开源 agent 框架 + 用户历史偏好 MCP 类", // v2 新增
          "summary": "...",             // v1 保留
          "workspace_help": "...",      // v1 保留
          "claude_usage": "...",        // v1 保留
          "hn_url": "...",              // v1 保留
          "summary_error": ""           // v1 保留
        }
      ],
      "error": null
    }
  ]
}
```

前端 `_render_news_item` 改动 (reviewer 反馈 #9, #13):
- 如 `ai_score` 存在, 在 title 右侧加 `<span title="{reason}">💡 {ai_score}</span>`
- `score` 原本渲染成 HN points (不变)
- stage badge 显示在 card 顶部 (🥶 cold / 🌡️ mid / 🔥 hot)

---

## 11. 历史持久化 (负例数据源)

### 11.1 ai-news-history.jsonl

**动机**: 原设计说"负例 = 未点赞 >= 7 天", 但 ai-news.json 每天覆写, 7 天前的条目 URL 消失, 负例池为空.

**存储语义 (纯 append-only)**:
每次 pipeline 跑完, 主 agent 把本次展示的所有 items append 到 jsonl, **允许同 url 重复行** (每次展示各 append 一行), 不做 in-place 更新.

**一行格式**:
```json
{"ts":"2026-04-20T10:12:00+09:00","source":"hackernews","url":"https://...","title":"...","desc":"..."}
```

**查询 (按需聚合)**:
```python
# ai_news/history.py
def get_negatives(source_id: str, feedback: dict, days: int = 7, limit: int = 30) -> list:
    """
    读 jsonl, 按 url 聚合 (first_ts=min, last_ts=max, count=行数),
    过滤: source == source_id AND url not in feedback.votes AND first_ts <= now - days,
    排序: count desc (曾被多次展示但从没点赞 = 更强负信号),
    取 limit 条.
    """
```

**文件大小控制**:
- 预计一天 append ~40 行, 60 天 ≈ 2400 行, 文件 < 1 MB
- v1 暂不主动清理; pipeline 在运行一段时间 (如 90 天) 后若体积问题再加清理逻辑 (可内嵌在 /loop 每周一次的 tick)

---

## 12. TG 通知

**沿用现有 MCP 插件** (`mcp__plugin_telegram_telegram__reply`). MCP 断连时 graceful skip (写日志不阻塞主流程).

消息模板:
```
[ai-news] 已刷新 {total} 则
HN {n1} · GitHub {n2} · 量子位 {n3} · iThome {n4}
阶段: HN cold · GitHub mid · 量子位 cold · iThome cold
dashboard: http://localhost:38080/#news
```

evolve 通知模板 (每次 evolve 触发时发):
```
[ai-news] {source} 已 evolve 到 v{N}
若最近推荐质量下降, 可手动回滚: cp source.md.v{N-1} source.md
```

---

## 13. Dashboard 改动

**最小增强**:
1. 删除 "刷新" 按钮 (setupNewsRefresh JS + POST /news/refresh 后端路由)
2. 每条目加 `💡 {ai_score}` 悬浮 tooltip 显示 reason (若 ai_score 存在)
3. 顶部显示 stage badge + 数据时间
   - "阶段: HN 🥶 · GitHub 🌡️ · 量子位 🥶 · iThome 🥶"
   - "数据更新: X 小时前" (读 ai-news.json 的 `updated_at` 字段, 不依赖心跳)

**不改动**:
- "有帮助" 投票按钮 (继续用 /news/vote, 继续写 ai-news-feedback.json)
- 现有条目展示结构

---

## 14. 错误处理 / 降级

| 故障点 | 行为 |
|---|---|
| 某源抓取失败 | 其他源继续, 该源 `error` 字段带错, items 空数组 |
| 某源 scorer subagent 失败 | 该源退化成冷启动行为 (原生排序) |
| 单条 WebFetch (Jina) 失败 | 摘要仅凭 title, `summary_error` 带错 |
| 单条 summary/analysis subagent 失败 | 该条对应字段空, `summary_error` 带错, 其他条目不受影响 |
| /loop 主 agent 崩 | **当天不抓新闻, 用户自己在 tmux 里发现后重启** (不做自动兜底) |
| TG MCP 断连 | 写日志不阻塞主流程, 新闻仍然正常写入 ai-news.json |
| evolve 失败 | 不覆盖旧 source.md, 记 log, 下次跑再试 |
| evolve 质量下降 | 用户手动 `cp source.md.v{N-1} source.md` 回滚 (不做自动回滚) |

整体失败: 不覆盖上一版 `ai-news.json`, 保证 dashboard 至少有昨天的数据.

---

## 15. 兜底机制 (v1 不做, 保留作为后续扩展)

v1 不实现以下兜底, 接受"/loop 挂了当天没抓到就算了"的简化立场:

- /loop 心跳监控 (独立 launchd job 检测 /loop 存活)
- Evolve 自动回滚 (点赞率监控 + 回到 source.md.v{N-1})
- 告警走 curl (脱离 MCP 依赖)

若上线后观察到 /loop 频繁挂或 evolve 经常改坏, 再按 §19 的方案加回.

---

## 16. 兼容性

| 资产 | 处理 |
|---|---|
| `fetch-ai-news.py` | 降级为"抓取层 debug 入口", 只跑 fetchers + filters, 输出到 `/tmp/` |
| `/news/refresh` 后端 | **删除** |
| `/news/vote` 后端 | 不改 (继续写 ai-news-feedback.json) |
| `ai-news-feedback.json` 格式 | 不改 |
| `ai-news.json` 格式 | 新增 `ai_score` / `reason` / `stage` / `stage_by_source`, 前端 graceful 处理缺失 |
| Dashboard `_render_news_panel` | 加 ai_score 悬浮 + stage badge + 数据更新时间显示 + 删除刷新按钮 |
| Dashboard JS `setupNewsRefresh` | **删除** |
| Dashboard JS `setupNewsVote` | 不改 |

---

## 17. 部署 / 启动

### 17.1 首次安装 (脚本化)

```bash
# 1. Python 模块
mkdir -p ~/.claude/hooks/ai_news/
# 写入 fetchers.py / filters.py / feedback.py / history.py / io.py / evolve.py

# 2. Skill + 数据目录
mkdir -p ~/.claude/skills/ai-news-fetch/
mkdir -p ~/.claude/skills/ai-news-filter/sources/{hackernews,github_trending,qbitai,ithome_tw}/
mkdir -p ~/.claude/skills/ai-news-filter/reference/
# 写入 SKILL.md 和每源 source.md / fetcher.yaml / examples.md 初始值

# 3. Subagents
mkdir -p ~/.claude/agents/
# 写入 news-scorer.md / news-summary.md / news-analysis.md / evolve-source-preferences.md

# 4. Dashboard 改动
# - 修改 usage_web_render.py (删除刷新按钮 render, 加 stage/updated_at 显示, 加 ai_score tooltip)
# - 修改 usage-web.py (删除 /news/refresh 路由)
# - 修改 usage-web.js (删除 setupNewsRefresh)

# 5. 冒烟测试
python3 ~/.claude/hooks/fetch-ai-news.py   # 抓取层 debug, 不跑 AI
# 检查 /tmp/ai-news-raw-*.json 是否符合预期
```

### 17.2 启动 /loop

```bash
tmux new -s ai-news
claude --model sonnet
# Claude Code 里输入:
/loop
# prompt 内容:
# "使用 ai-news-fetch skill. 每次唤醒时按 skill 的算法判断是否到 10:00,
#  命中窗口 (10:00-10:30) 跑完整 pipeline; 否则 ScheduleWakeup 到下一个整点
#  (delaySeconds = min(3600, delta_to_next_10am_seconds))."
```

主 agent 每次 /loop tick 读 `ai-news-fetch/SKILL.md` 里的详细算法和编排步骤.

---

## 18. 验证计划

### 18.1 分层冒烟

1. **抓取层**: `python3 ~/.claude/hooks/fetch-ai-news.py` → 检查 `/tmp/ai-news-raw-*.json` 格式正确, 4 源都有数据.
2. **评分层**: 手动在 Claude Code 里派 news-scorer subagent 一次, 输入模拟候选 + 模拟 source.md + 模拟 examples, 验证 JSON 输出结构.
3. **摘要/分析层**: 派 news-summary / news-analysis 各一次, 验证输出格式.
4. **完整 pipeline**: 在 tmux 里启动 /loop, 人工把"目标 10:00"改成"未来 3 分钟", 观察全流程跑通 → TG 收到通知 → ai-news.json 字段齐全 → dashboard 正常渲染.
5. **evolve**: 手动灌 50 条 HN 反馈 + 模拟"距上次 evolve 新增 20 条" → 检查 evolve 是否触发 + source.md 被重写 + `source.md.v{N-1}` 备份存在 + `ai-news-evolve-log.jsonl` 有记录.
6. **手动回滚**: `cp source.md.v{N-1} source.md` → 下次 /loop 跑时使用回滚后的偏好.

### 18.2 长期监控

- 7 天: 反馈数 / scorer 触发次数 / Top 10 命中率 (你觉得是不是想看的)
- 30 天: 是否如期进入中启动 / 热启动 / evolve 触发

---

## 19. 后续扩展 (v2 之后, 不属于本 spec)

- **兜底机制** (§15 延后项):
  - /loop 心跳监控 + launchd 每小时检测 + curl 告警 (独立于 MCP)
  - Evolve 自动回滚 (点赞率下降 50% 阈值 + 7 天观察期)
- Twitter / Threads (自建 rsshub Docker)
- Reddit r/LocalLLaMA / r/ClaudeAI
- arxiv AI 论文 RSS (cs.AI / cs.CL)
- Dashboard 源偏好编辑器 (web 直接改 source.md)
- Opus 复核边界条目 (Top 10 / 11 位分差 < 1 时复核)
- 跨源去重 (同 URL / 高度相似标题合并)
- A/B prompt 自动对比
- Codex 作为第二评分员 (双 AI 交叉验证)

---

## 20. 开放问题 (实施阶段决)

1. `/loop` 启动 prompt 的具体措辞 (§17.2 是草稿, 实施时根据 /loop skill 实际行为微调)
2. `ai-news-history.jsonl` 60 天清理阈值是否足够
3. Agent tool 实际并行上限 (spec 按 10 并发假设, 需要实测确认, 不足则增加批次数量)
4. Claude Code 启动参数 `--model sonnet` 和 `/loop` 内 subagent 指定 `model:` 的交互: subagent 的 model 是否真的覆盖主 agent 模型? (§4 假设如此, 需要施工第一周 smoke test)
