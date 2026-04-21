# AI 大事 v2 Implementation Plan

> **For agentic workers:** 这份 plan 由 **/loop 自主执行**, 不是人工 subagent-driven-development. 每次 /loop 唤醒读 `~/Desktop/ai-project/progress/progress.json`, 按 bug-first 机制处理 (见下). 任务标记用 `- [ ]` checkbox.

**Goal:** 按 `~/Desktop/ai-project/docs/spec.md` (spec v4) 实施 AI 大事 v2, 并把整个"统计系统"(dashboard + usage 追踪 + AI 大事 + 数据) 迁移到独立项目 `~/Desktop/ai-project/` 下做 git 版本化管理. /loop 每天 10am 自动抓 4 源、按反馈 few-shot 评分、Top 10 上 Haiku 摘要 + Opus 分析、写 ai-news.json、发 TG、按阶段触发 evolve.

**项目结构**:

```
~/Desktop/ai-project/
├── .claude/{skills/{ai-news-fetch,ai-news-filter},agents/news-*}   # 项目级 skill/agent
├── hooks/            # 所有 Python 代码 (新 + 从 ~/.claude/hooks/ 迁)
│   ├── ai_news/
│   ├── fetch-ai-news.py
│   ├── usage-web.py / usage_web_*.py / usage-web.{js,css}
│   └── usage-*.sh
├── data/             # 从 ~/.claude/usage-stats/ 迁 (gitignore)
├── docs/{spec,plan}.md
├── progress/         # /loop 状态 (gitignore)
│   ├── progress.json      # 机器读, 断点恢复
│   ├── progress.md        # 人读, 每 task 摘要
│   ├── NEED-HUMAN-INPUT.md  # 挂起通信
│   └── logs/task-X.Y.log  # 每 task subprocess 输出
└── .gitignore

~/.claude/hooks/       # 迁后只留 Claude Code 机制 hook
├── pre-compact.sh / post-compact.sh / session-start.sh
```

**Architecture:** 编排在 skill 里由主 agent (Sonnet) 执行, 重推理全部派 subagent (Haiku/Opus, model 强制). 纯工程任务走 Python 模块 (`~/Desktop/ai-project/hooks/ai_news/`). 数据目录 `~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/<id>/` 每源独立. 反馈演化 (evolve) 由主 agent 触发条件后派专用 subagent 重写 `source.md`.

**Tech Stack:** Python 3 + PyYAML, Claude Code Agent tool + subagent md, 项目级 skill 机制, /loop dynamic mode, MCP telegram plugin, git.

---

## /loop 执行约束 (bug-first + 当轮不结束)

每次 /loop 唤醒严格按此流程:

```
on_wakeup():
  # 1. Bug 优先: 检查前面轮次留下的未决状态
  progress = read(~/Desktop/ai-project/progress/progress.json)

  if progress.blocked_on:
    blocked = progress.blocked_on

    if blocked.type == "MANUAL_WAIT":
      # 读 NEED-HUMAN-INPUT.md 看 resolved 字段
      if resolved == true:
        progress.blocked_on = None
        继续到第 2 步
      else:
        ScheduleWakeup(7200s)  # 2h 后再查
        return  # 本轮结束 (合法)

    if blocked.type == "AUTO_FAIL":
      # /loop 自己能修的 bug, 在本轮内修
      retry_count = progress.error_count
      if retry_count < 3:
        诊断 log + 尝试修复
        if 修好:
          progress.blocked_on = None
          progress.error_count = 0
          继续到第 2 步
        else:
          progress.error_count += 1
          # 本轮继续 retry, 不 ScheduleWakeup
          loop 回第 1 步
      else:
        # 3 次修不好, 转 MANUAL
        write NEED-HUMAN-INPUT.md
        progress.blocked_on = {type: "MANUAL_WAIT", ...}
        ScheduleWakeup(7200s)
        return  # 本轮结束 (合法)

  # 2. 无 blocked, 跑下一个 task
  next_task = find_first_unchecked_task_in(plan.md)
  run_task(next_task)  # 包含 test + commit

  # 3. 任务完成校验
  if all_tests_pass AND file_creates_succeed AND commit_succeed:
    mark plan.md 对应 checkbox [x]
    update progress.{json,md} + append log
    ScheduleWakeup(60s)  # 本轮合法结束, 下一轮立刻开始下一个 task
  else:
    # 任务失败, 本轮不能结束
    progress.blocked_on = {type: "AUTO_FAIL", task: X.Y, error: ...}
    progress.error_count = 1
    loop 回第 1 步  # 立刻进入 retry 流程, 不 ScheduleWakeup
```

**关键约束**:
- 只有两种情况 ScheduleWakeup (本轮 /loop 合法结束): **(a)** task 完成 + 测试通过 + commit 成功; **(b)** BLOCKED 转 MANUAL 等人
- 任务失败的 retry 在**同一轮**内做, 不浪费下一次唤醒
- 单次唤醒 >= 45 分钟强制暂停 (避免 context 爆) → 标 BLOCKED, 下次唤醒从这里继续
- **禁止 /loop 为了通过测试而改测试** (作弊, 藏 bug)
- **禁止 /loop 跳过 MANUAL 任务** (写 NEED-HUMAN-INPUT 挂起, 不能假装完成)

---

## /loop 启动前的人工准备 (一次性, 必须先做)

在 /loop 可以开始执行 plan 之前, 用户手动完成:

```bash
# 1. 建项目目录 + git init
mkdir -p ~/Desktop/ai-project/{hooks,data,docs,progress/logs,.claude/skills,.claude/agents}
cd ~/Desktop/ai-project
git init
echo -e "data/\nprogress/\n__pycache__/\n*.bak\n*.tmp\n.DS_Store" > .gitignore
git add .gitignore && git commit -m "chore: init repo"

# 2. 迁移 spec + plan 进项目 docs/
mv ~/Desktop/2026-04-20-ai-news-v2-design.md ~/Desktop/ai-project/docs/spec.md
mv ~/Desktop/2026-04-21-ai-news-v2-plan.md ~/Desktop/ai-project/docs/plan.md
cd ~/Desktop/ai-project && git add docs/ && git commit -m "docs: import spec + plan"

# 3. 初始化 progress
cat > ~/Desktop/ai-project/progress/progress.json <<'EOF'
{
  "current_task": null,
  "last_completed": null,
  "blocked_on": null,
  "error_count": 0,
  "started_at": null,
  "last_heartbeat": null
}
EOF
touch ~/Desktop/ai-project/progress/progress.md

# 4. 写 README + 启动 /loop
cat > ~/Desktop/ai-project/README.md <<'EOF'
# ai-project — AI / 统计系统独立项目
详见 docs/plan.md. /loop 执行中, 进度看 progress/progress.md.
EOF

# 5. 启动生产 tmux + /loop
tmux new -s ai-project-exec
cd ~/Desktop/ai-project
claude --model sonnet
# 在 Claude Code 里:
/loop
# prompt:
# "按 docs/plan.md 执行. 每次唤醒先读 progress/progress.json,
#  按 plan 开头的 '执行约束 (bug-first + 当轮不结束)' 流程做事.
#  遇 MANUAL 任务写 progress/NEED-HUMAN-INPUT.md 挂起 + TG 通知."
```

完成上面 5 步后, /loop 自动接管. 你此后只在以下情况介入:

- /loop 写了 `progress/NEED-HUMAN-INPUT.md` + TG 通知 → 去处理, 处理完在文件顶加 `resolved: true`
- 每天看一眼 `progress/progress.md` 了解进度

---

**任务标签规则**:
- `[AUTO]` = 纯代码写 + Python 单元测试可验证, /loop 能自主跑完, 无需人工介入
- `[MANUAL]` = 涉及 Claude Code 交互 / 浏览器 / 外部账单判断 / 生产长跑. /loop 处理流程:
  1. 读 Task 的 Steps 列表, 判断每步是 "/loop 能自动做的预处理" (如 subprocess.run / Write 文件 / curl 自检) 还是 "必须人工做" (如 "浏览器打开"/"看 Anthropic dashboard"/"tmux new + claude --model ..."/"长时间观察")
  2. 能自动的预处理先跑 (如 Task 2.0a 先临时写 news-scorer.md; Task 0.5 先 subprocess 启 dashboard + curl 自检)
  3. 剩下人工步骤打包进 `~/Desktop/ai-project/progress/NEED-HUMAN-INPUT.md` 的"你要做的"段
  4. 发 TG 通知: "[ai-project-exec] Task X.Y 需要人工, 详见 progress/NEED-HUMAN-INPUT.md"
  5. `ScheduleWakeup(7200s)` 挂起, 下次唤醒读文件顶的 `resolved:` 字段
  6. Resolved 后 /loop 读 resolved 下的 `verdict:` (PASS/FAIL) 或人类附加说明, 决定:
     - `verdict: PASS` 或无 verdict → mark checkbox [x], 进下一 task
     - `verdict: FAIL` → blocked_on 转 "AUTO_FAIL", 诊断 + 重试 (本轮 retry, ≤ 3 次)
  7. 不能因 /loop 自己想不通而跳过 MANUAL; 实在挂太久 (48h+), 什么也不做, 继续挂

**分 6 个 chunks**. Chunk 0 已手动完成, /loop 实际执行从 Chunk 1 开始:
- **Chunk 0: 项目迁移 + git init** — **已手动完成**, /loop 跳过本 chunk
- Chunk 1: Python 基础模块 + fetcher.yaml 前置 (全 AUTO, 严格串行) — **/loop 从这里开始**
- Chunk 2: 架构根基 smoke (model 覆盖 + 并发上限 MANUAL) + Subagent 契约 + Skill 骨架
- Chunk 3: 每源 source.md / examples.md 初值 (AUTO) + 抓取冒烟 (MANUAL)
- Chunk 4: Dashboard 改动 (AUTO 写代码改项目内文件, MANUAL 浏览器验证)
- Chunk 5: 集成冒烟 (sentinel 机制) + /loop 长跑 + 监控 (全 MANUAL)

**约束**:
- `~/Desktop/ai-project/` 是 git 仓库, 每个 AUTO task 完成后 `git commit -m "..."`
- 测试路径: `~/Desktop/ai-project/hooks/ai_news/tests/*.py`, 用 Python stdlib `unittest`. 跑法: `cd ~/Desktop/ai-project/hooks && python3 -m unittest discover ai_news/tests -v`
- 生产文件禁止带 emoji (CLAUDE.md 规则); plan / 测试 / progress / logs / NEED-HUMAN-INPUT 例外 (可有 emoji)

---

## Progress / NEED-HUMAN-INPUT 文件格式

### progress/progress.json

```json
{
  "current_task": "1.3",
  "last_completed": "1.2",
  "blocked_on": null,
  "error_count": 0,
  "started_at": "2026-04-21T02:00:00+09:00",
  "last_heartbeat": "2026-04-21T03:12:00+09:00"
}
```

`blocked_on` 可能值:
- `null` — 没 blocked, 可以继续
- `{"type": "MANUAL_WAIT", "task": "2.0a", "created_at": "...", "need_human_input_path": "..."}` — MANUAL 挂起, 等 resolved
- `{"type": "AUTO_FAIL", "task": "1.3", "retry_count": 2, "error": "test 2/3 fail", "last_log": "logs/task-1.3.log"}` — AUTO 任务失败 retry 中

### progress/progress.md

按时间倒序 (最新在顶), 每 task 一段:

```markdown
## 2026-04-21 03:12 Task 1.3 ✓
- 写 hooks/ai_news/fetchers.py 的 HN Algolia 部分 (~80 行)
- HTTP 冒烟抓到 5 条 HN 条目
- test_filters.py 4/4 通过
- commit: abc1234 "feat(ai_news): add fetchers.fetch_hn_algolia"
- log: progress/logs/task-1.3.log

## 2026-04-21 03:08 Task 1.2 ✓
- ...
```

### progress/NEED-HUMAN-INPUT.md

```markdown
resolved: false

## Task 2.0a: 需要人工验证 subagent model 覆盖

/loop 已自动派遣 news-scorer subagent (haiku-4-5) 一次, 跑完了冒烟.
但判断是否按 Haiku 计费需要你去 Anthropic dashboard 看.

### 你要做的:
1. 打开 https://console.anthropic.com/ → Usage
2. 找最近 5 分钟的调用, 看 model 字段是 "claude-haiku-4-5" 还是被覆盖成 "claude-sonnet-4-6"
3. 在本文件顶部改 `resolved: false` → `resolved: true`
   - 若 model 是 haiku, 额外加一行: `verdict: PASS`
   - 若 model 是 sonnet, 加 `verdict: FAIL` — 整个架构要推倒, 向 user 反馈

### 日志:
- progress/logs/task-2.0a.log

### /loop 状态:
- 已 ScheduleWakeup 2h, 下次唤醒会读本文件看 resolved.
- 若急处理完, 可以立即向 /loop 会话发消息 "resolved" 让它立刻唤醒.
```

### progress/logs/task-X.Y.log

每个 task 执行时的原始 subprocess stdout/stderr + 关键时间戳. 出 bug 时查此文件排错.

---

---

## Chunk 0: 项目迁移 + git init — 已手动完成 (2026-04-21)

迁移由用户在 /loop 启动前手动完成, 本 chunk 无 task 需 /loop 执行. /loop 扫描 plan 时直接跳到 Chunk 1 Task 1.1.

**已完成动作 (git log 可查)**:

- `~/Desktop/ai-project/` 项目目录 + git init + .gitignore
- spec + plan 迁入 `docs/`
- `progress/progress.json` + `progress.md` 初始化
- `README.md` 写入
- 停原位 dashboard (`~/.claude/hooks/usage-web.py`)
- cp 代码 + 数据到项目 (`hooks/`, `data/`)
- 改所有硬编码路径常量: `~/.claude/usage-stats/` → `~/Desktop/ai-project/data/`, `~/.claude/hooks/fetch-ai-news.py` → `~/Desktop/ai-project/hooks/fetch-ai-news.py`
  - 6 个 .py 文件 + 4 个 .sh 脚本
- 启动新位置 dashboard (`python3 ~/Desktop/ai-project/hooks/usage-web.py`), HTTP 200 + HTML 渲染正常
- mv 原位 15 个旧文件到 `~/.claude/hooks/.migrated-to-ai-project-20260421/`
- 保留 `~/.claude/hooks/` 顶层 4 个文件:
  - `pre-compact.sh` / `post-compact.sh` / `session-start.sh` — Claude Code 机制 hook
  - `usage-tracker.sh` — Claude Code settings.json 调用, LOG_DIR 已改指向项目 `data/`
- git commit 全部变更

**git log (Chunk 0 相关 commits)**:

```
1db513b refactor(hooks): rewire paths from ~/.claude/ to ~/Desktop/ai-project/
c2cd651 chore(migrate): copy stats system code from ~/.claude/hooks/
8f942ec docs: add README
251b5e4 docs: import spec + plan
74888d9 chore: init repo
```

**新位置 dashboard**: http://localhost:38080 — 用户浏览器验证所有 tab 后即可让 /loop 启动施工.

---

## Chunk 1: Python 基础模块

**范围**: `~/Desktop/ai-project/hooks/ai_news/` 下 6 个模块 (`fetchers.py` / `filters.py` / `feedback.py` / `history.py` / `io.py` / `evolve.py`) + 单元测试 + 4 个 `fetcher.yaml` (前置, 让抓取冒烟有 config 可读). 所有任务 `[AUTO]`.

**执行约束 (reviewer 反馈 High #5)**:
- **Task 1.1 → 1.13 必须严格串行**, 不得并行派 subagent.
- 理由: Task 1.3-1.7 都写 `fetchers.py` 同一文件 (HN → GH → RSS → Jina → fetch_all 依次 append), 并行改同文件会冲突.
- subagent-driven-development 执行时声明 "Chunk 1 single-threaded", 先跑完 1.1 再派 1.2, 依此类推.

**依赖**: 沿用 v1 的 `~/Desktop/ai-project/hooks/fetch-ai-news.py` (534 行) 中的抓取 + 正则逻辑. 新增一个三方库 (PyYAML).

**文件结构**:
```
~/Desktop/ai-project/hooks/ai_news/
├── __init__.py
├── fetchers.py        # fetch_hn_algolia / fetch_github_trending / fetch_rss / fetch_article_text / fetch_all
├── filters.py         # HARD_NOISE_RE 等, apply_hard_filter(items) -> items
├── feedback.py        # load_feedback / get_stage / get_positives / get_negatives / build_examples_inline
├── history.py         # append_items / aggregate_by_url / get_negatives_from_history
├── io.py              # read_ai_news / write_ai_news_atomic / read_source_md / write_source_md_atomic
├── evolve.py          # backup_source / write_evolve_log / load_source_frontmatter
└── tests/
    ├── __init__.py
    ├── test_filters.py
    ├── test_feedback.py
    ├── test_history.py
    ├── test_io.py
    └── test_evolve.py
```

---

### Task 1.1: [AUTO] 安装 PyYAML + 创建目录骨架 + 4 个 fetcher.yaml

**Files:**
- Create: `~/Desktop/ai-project/hooks/ai_news/__init__.py`
- Create: `~/Desktop/ai-project/hooks/ai_news/tests/__init__.py`
- Create: `~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/hackernews/fetcher.yaml`
- Create: `~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/github_trending/fetcher.yaml`
- Create: `~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/qbitai/fetcher.yaml`
- Create: `~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/ithome_tw/fetcher.yaml`

- [ ] **Step 1: 安装 PyYAML 硬依赖** (reviewer 反馈 Blocker #1)

Run: `pip3 install PyYAML`
Expected: 安装成功或 "already satisfied".

验证: `python3 -c "import yaml; print(yaml.__version__)"`
Expected: 打印版本号.

若失败: 使用 `pip3 install --user PyYAML` 或 `python3 -m pip install PyYAML`.

- [ ] **Step 2: 建 Python 模块目录 + 空 init**

```bash
mkdir -p ~/Desktop/ai-project/hooks/ai_news/tests
touch ~/Desktop/ai-project/hooks/ai_news/__init__.py
touch ~/Desktop/ai-project/hooks/ai_news/tests/__init__.py
```

- [ ] **Step 3: 建 sources 数据目录**

```bash
mkdir -p ~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/{hackernews,github_trending,qbitai,ithome_tw}
mkdir -p ~/Desktop/ai-project/.claude/skills/ai-news-filter/reference
```

- [ ] **Step 4: 写 4 个 fetcher.yaml** (前置到 Chunk 1, 避免 Chunk 3 之前抓取无 config)

`~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/hackernews/fetcher.yaml`:
```yaml
type: hn_algolia
params:
  query: "AI OR Claude OR Anthropic OR LLM OR MCP OR OpenAI OR Gemini OR DeepSeek"
  sort_by: points
  time_window_hours: 48
  min_points: 30
  limit: 20
```

`~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/github_trending/fetcher.yaml`:
```yaml
type: github_trending
params:
  since: daily
  limit: 20
```

`~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/qbitai/fetcher.yaml`:
```yaml
type: rss
params:
  url: https://www.qbitai.com/feed
  time_window_hours: 48
  limit: 15
```

`~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/ithome_tw/fetcher.yaml`:
```yaml
type: rss
params:
  url: https://www.ithome.com.tw/rss
  time_window_hours: 48
  limit: 15
```

- [ ] **Step 5: 验证**

Run: `ls ~/Desktop/ai-project/hooks/ai_news/ ~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/*/fetcher.yaml`
Expected: Python 目录存在 + 4 个 fetcher.yaml 都存在.

- [ ] **Step 6: Mark complete**

**注意**: Chunk 3 的 Task 3.1-3.4 只写 `source.md` + `examples.md`, 不再写 fetcher.yaml (已前置到这里).

---

### Task 1.2: [AUTO] filters.py — 硬规则过滤 (移植 v1)

**Files:**
- Create: `~/Desktop/ai-project/hooks/ai_news/filters.py`
- Create: `~/Desktop/ai-project/hooks/ai_news/tests/test_filters.py`
- Reference: `~/Desktop/ai-project/hooks/fetch-ai-news.py:45-108` (v1 原正则)

- [ ] **Step 1: 写测试 `tests/test_filters.py`**

```python
import unittest
from ai_news.filters import is_pure_ai_news, apply_hard_filter


class TestIsPureAiNews(unittest.TestCase):
    def test_hard_noise_rejects_vulnerability(self):
        self.assertFalse(is_pure_ai_news("GPT 漏洞导致数据泄露"))
        self.assertFalse(is_pure_ai_news("OpenAI CVE-2024-xxxx 披露"))

    def test_core_ai_passes_even_with_soft_noise(self):
        # "融資" 是 soft noise, 但 Claude 是 core AI 产品
        self.assertTrue(is_pure_ai_news("Claude 新版本发布"))

    def test_soft_noise_rejects_when_only_secondary_keyword(self):
        # "LLM" 是次级关键词, "融資" 是 soft noise → 剔除
        self.assertFalse(is_pure_ai_news("某 LLM 公司融資 1 億美元"))

    def test_no_ai_keyword_rejects(self):
        self.assertFalse(is_pure_ai_news("iPhone 新机发布"))


class TestApplyHardFilter(unittest.TestCase):
    def test_filter_removes_hard_noise(self):
        items = [
            {"title": "Claude 4.7 发布", "url": "a"},
            {"title": "GPT 漏洞 CVE-2024", "url": "b"},
            {"title": "量子位融资 1 亿", "url": "c"},
        ]
        out = apply_hard_filter(items)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["url"], "a")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test 验证它失败**

Run: `cd ~/Desktop/ai-project/hooks && python -m unittest ai_news.tests.test_filters -v`
Expected: `ModuleNotFoundError: No module named 'ai_news.filters'`

- [ ] **Step 3: 写 `filters.py`**

```python
"""硬规则过滤 (沿用 v1 fetch-ai-news.py 的正则黑白名单).

两层过滤:
1. HARD_NOISE_RE 命中 → 直接剔除 (漏洞/攻击/融资/产业)
2. CORE_AI_RE 命中 → keep (强信号, 忽略 soft noise)
3. AI_PRODUCT_RE 命中 + 无 soft noise → keep
"""
import re

CORE_AI_RE = re.compile(
    r"(Claude|Anthropic|ChatGPT|OpenAI|GPT-|Sora|Gemini|Bard|DeepSeek|Qwen|"
    r"LLaMA|Llama|Mistral|Grok|Copilot|Cursor|Perplexity|Midjourney|Firefly|"
    r"Stable\s*Diffusion|Hugging\s*Face|Kimi|Doubao|豆包|文心|通義|通义|"
    r"智譜|智谱|GLM|Minimax|百川|"
    r"Opus|Sonnet|Haiku)",
    re.I,
)

AI_PRODUCT_RE = re.compile(
    r"(" + CORE_AI_RE.pattern.strip("()") + r"|"
    r"o1\b|o3\b|o4\b|o5\b|Yi\b|MCP|agent|agentic|"
    r"大(?:型|语|語)言模型|大模型|生成式|人工智慧|人工智能|LLM)",
    re.I,
)

_NOISE_TERMS = [
    "融資", "融资", "併購", "并购", "IPO", "收購", "收购", "股價", "股价",
    "估值", "投資人", "投资人", "私募", "募資", "募资", "季報", "季报",
    "財報", "财报", "營收", "营收", "業績", "业绩", "淨利", "净利",
    "工廠", "工厂", "產業鏈", "产业链", "供應鏈", "供应链", "晶圓", "晶圆",
    "代工", "製造業", "制造业", "產業界", "产业界",
    "汽車", "汽车", "電動車", "电动车", "自動駕駛", "自动驾驶", "造車", "造车",
    "車企", "车企", "NOA", "自駕", "自驾", "智駕", "智驾", "充電樁", "充电桩",
    "ESG", "淨零", "净零", "永續", "永续", "減碳", "减碳", "碳排",
    "資安", "资安", "漏洞", "駭客", "骇客", "攻擊", "攻击", "惡意", "恶意",
    "malware", "ransomware", "CVE", "NKAbuse", "詐騙", "诈骗", "釣魚", "钓鱼",
    "FIDO", "KYA", "KYC", "GDPR", "合規", "合规", "審計", "审计",
    "制裁", "禁令", "關稅", "关税", "貿易戰", "贸易战", "出口管制",
    "醫療", "医疗", "診斷", "诊断", "臨床", "临床",
    "週報", "周报", "回顧", "回顾",
]
NOISE_RE = re.compile("|".join(re.escape(t) for t in _NOISE_TERMS), re.I)

_HARD_NOISE_TERMS = [
    "漏洞", "駭客", "骇客", "攻擊", "攻击", "惡意", "恶意", "malware",
    "ransomware", "詐騙", "诈骗", "CVE", "NKAbuse", "零時差", "零日",
    "併購", "并购", "融資", "融资", "IPO", "收購", "收购", "股價", "股价",
    "關稅", "关税", "制裁",
]
HARD_NOISE_RE = re.compile("|".join(re.escape(t) for t in _HARD_NOISE_TERMS), re.I)


def is_pure_ai_news(title: str, desc: str = "") -> bool:
    if HARD_NOISE_RE.search(title):
        return False
    if CORE_AI_RE.search(title):
        return True
    if AI_PRODUCT_RE.search(title) and not NOISE_RE.search(title):
        return True
    return False


def apply_hard_filter(items: list) -> list:
    """对 items 列表应用硬规则过滤, 返回过滤后的列表."""
    out = []
    for it in items:
        title = it.get("title", "")
        desc = it.get("desc", "")
        if is_pure_ai_news(title, desc):
            out.append(it)
    return out
```

- [ ] **Step 4: Run test 验证通过**

Run: `cd ~/Desktop/ai-project/hooks && python -m unittest ai_news.tests.test_filters -v`
Expected: 4 tests OK

- [ ] **Step 5: Mark complete**

---

### Task 1.3: [AUTO] fetchers.py — HN Algolia

**Files:**
- Create: `~/Desktop/ai-project/hooks/ai_news/fetchers.py`
- Reference: `~/Desktop/ai-project/hooks/fetch-ai-news.py:127-166`

- [ ] **Step 1: 写 fetchers.py 的 HN 部分 (先不加测试, HTTP 调用难 unit test)**

```python
"""新闻抓取函数. 每个函数接受 params dict (来自 fetcher.yaml), 返回 items list.

items 每条包含: title, url, desc, ts (ISO), 以及源特有字段 (HN: score/comments, GH: today_stars_int/lang).
"""
import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser

TIMEOUT = 12
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) claude-code-dashboard/2.0"
JINA_READER_PREFIX = "https://r.jina.ai/"


def _fetch(url: str, headers=None, timeout=TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def fetch_hn_algolia(params: dict) -> list:
    """HN Algolia API. params:
    - query: 关键词 (用于本地 re 过滤)
    - sort_by: 'points' | 'comments' | 'created_at'
    - time_window_hours: int
    - min_points: int
    - limit: int (候选上限)
    """
    import re as _re
    query = params.get("query", "")
    sort_by = params.get("sort_by", "points")
    window = int(params.get("time_window_hours", 48))
    min_points = int(params.get("min_points", 30))
    limit = int(params.get("limit", 20))

    all_hits = {}
    # 1) front_page
    url1 = "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=50"
    try:
        for h in json.loads(_fetch(url1)).get("hits", []):
            all_hits[h.get("objectID")] = h
    except Exception:
        pass
    # 2) 最近 N 小时按分数降序
    since = int(datetime.now(timezone.utc).timestamp()) - 3600 * window
    url2 = (
        f"https://hn.algolia.com/api/v1/search?tags=story"
        f"&numericFilters=points%3E{min_points},created_at_i%3E{since}&hitsPerPage=50"
    )
    try:
        for h in json.loads(_fetch(url2)).get("hits", []):
            all_hits[h.get("objectID")] = h
    except Exception:
        pass

    # 本地 keyword 过滤
    kw_re = _re.compile(query.replace(" OR ", "|").replace(" ", r"\s*"), _re.I) if query else None
    items = []
    for h in all_hits.values():
        title = (h.get("title") or h.get("story_title") or "").strip()
        if not title:
            continue
        if kw_re and not kw_re.search(title):
            continue
        items.append({
            "title": title,
            "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
            "hn_url": f"https://news.ycombinator.com/item?id={h.get('objectID')}",
            "score": int(h.get("points", 0) or 0),
            "comments": int(h.get("num_comments", 0) or 0),
            "ts": h.get("created_at", ""),
            "author": h.get("author", ""),
            "desc": "",
        })
    # sort
    key_map = {
        "points": lambda x: x["score"],
        "comments": lambda x: x["comments"],
        "created_at": lambda x: x["ts"],
    }
    items.sort(key=key_map.get(sort_by, key_map["points"]), reverse=True)
    return items[:limit]
```

- [ ] **Step 2: 手动冒烟验证 HN fetcher 能拿到数据**

Run:
```bash
cd ~/Desktop/ai-project/hooks && python3 -c "
from ai_news.fetchers import fetch_hn_algolia
items = fetch_hn_algolia({'query': 'AI OR Claude OR LLM', 'sort_by': 'points', 'time_window_hours': 48, 'min_points': 30, 'limit': 5})
import json; print(json.dumps(items[:2], ensure_ascii=False, indent=2))
"
```
Expected: 打印 2 条 HN 条目 JSON, 每条有 title/url/score/comments/ts.

- [ ] **Step 3: Mark complete**

---

### Task 1.4: [AUTO] fetchers.py — GitHub Trending (today_stars_int 修复)

**Files:**
- Modify: `~/Desktop/ai-project/hooks/ai_news/fetchers.py` (append 函数)
- Reference: `~/Desktop/ai-project/hooks/fetch-ai-news.py:169-272` (v1 HTML parser)

**关键修复**: v1 的 `today_stars` 是字符串 `"123 stars today"`, 字典序排 "9" > "123". v2 必须新增 `today_stars_int` 字段.

- [ ] **Step 1: append GitHub Trending parser + fetch_github_trending() 函数到 fetchers.py**

```python
# 追加到 fetchers.py 末尾

GITHUB_TRENDING_URL_TPL = "https://github.com/trending?since={since}"


class _TrendingParser(HTMLParser):
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
            self._cur = {"title": "", "url": "", "desc": "", "lang": "",
                         "stars": "", "today_stars": "", "today_stars_int": 0}
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
            ts = "".join(self._buf).strip()
            self._cur["today_stars"] = ts
            # 关键修复: 转 int
            m = re.search(r"\d+", ts.replace(",", ""))
            self._cur["today_stars_int"] = int(m.group()) if m else 0
            self._capture = None; self._buf = []
        elif tag == "article" and self._in_article:
            if self._cur and self._cur["title"]:
                self.items.append(self._cur)
            self._in_article = False
            self._cur = None
            self._capture = None
            self._buf = []


def fetch_github_trending(params: dict) -> list:
    since = params.get("since", "daily")       # daily | weekly | monthly
    limit = int(params.get("limit", 20))
    url = GITHUB_TRENDING_URL_TPL.format(since=since)
    raw = _fetch(url).decode("utf-8", errors="ignore")
    p = _TrendingParser()
    p.feed(raw)
    items = []
    for it in p.items[:limit]:
        items.append({
            "title": it["title"],
            "url": it["url"],
            "desc": (it["desc"] or "")[:200],
            "lang": it["lang"],
            "stars": it["stars"],
            "today_stars": it["today_stars"],
            "today_stars_int": it["today_stars_int"],
        })
    # 按 today_stars_int 降序 (int 排序, 不会出现字典序 bug)
    items.sort(key=lambda x: x["today_stars_int"], reverse=True)
    return items
```

- [ ] **Step 2: 写单元测试 `tests/test_fetchers.py`** (只测 today_stars_int 解析, 不测 HTTP)

```python
import unittest
from ai_news.fetchers import _TrendingParser


class TestTodayStarsInt(unittest.TestCase):
    def test_parses_today_stars_as_int(self):
        html = """
        <article class="Box-row">
          <h2><a href="/owner/repo">owner/repo</a></h2>
          <p class="col-9">desc</p>
          <a class="Link--muted" href="/owner/repo/stargazers">1,234</a>
          <span class="d-inline-block float-sm-right">123 stars today</span>
        </article>
        <article class="Box-row">
          <h2><a href="/a/b">a/b</a></h2>
          <p class="col-9">desc</p>
          <a class="Link--muted" href="/a/b/stargazers">9</a>
          <span class="d-inline-block float-sm-right">9 stars today</span>
        </article>
        """
        p = _TrendingParser()
        p.feed(html)
        self.assertEqual(p.items[0]["today_stars_int"], 123)
        self.assertEqual(p.items[1]["today_stars_int"], 9)
        # 排序 (123 > 9) 不出现字典序 bug
        p.items.sort(key=lambda x: x["today_stars_int"], reverse=True)
        self.assertEqual(p.items[0]["today_stars_int"], 123)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test 验证通过**

Run: `cd ~/Desktop/ai-project/hooks && python -m unittest ai_news.tests.test_fetchers -v`
Expected: 1 test OK

- [ ] **Step 4: Mark complete**

---

### Task 1.5: [AUTO] fetchers.py — RSS (qbitai / ithome_tw) + 通用 fetch_rss()

**Files:**
- Modify: `~/Desktop/ai-project/hooks/ai_news/fetchers.py`
- Reference: `~/Desktop/ai-project/hooks/fetch-ai-news.py:275-348` (v1 RSS parser)

- [ ] **Step 1: append RSS parser + fetch_rss() 到 fetchers.py**

```python
# 追加到 fetchers.py 末尾

def _parse_rss2(xml_bytes: bytes, max_items: int = 20) -> list:
    """通用 RSS 2.0 <channel><item> 解析. 返回 [{title,url,desc,ts,author}]."""
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


def fetch_rss(params: dict) -> list:
    """通用 RSS 抓取. params:
    - url: RSS 地址
    - time_window_hours: 只保留这个窗口内的条目 (按 pubDate)
    - limit: 最多返回多少条
    """
    url = params["url"]
    window = int(params.get("time_window_hours", 48))
    limit = int(params.get("limit", 15))
    raw = _fetch(url)
    items = _parse_rss2(raw, max_items=max(50, limit * 2))

    # 时间窗过滤
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window)
    kept = []
    for it in items:
        try:
            ts_dt = datetime.fromisoformat(it["ts"].replace("Z", "+00:00"))
            if ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=timezone.utc)
            if ts_dt >= cutoff:
                kept.append(it)
        except Exception:
            kept.append(it)  # 解析不出时间的保留
    return kept[:limit]
```

- [ ] **Step 2: 手动冒烟**

Run:
```bash
cd ~/Desktop/ai-project/hooks && python3 -c "
from ai_news.fetchers import fetch_rss
items = fetch_rss({'url': 'https://www.qbitai.com/feed', 'time_window_hours': 72, 'limit': 5})
import json; print(json.dumps(items[:2], ensure_ascii=False, indent=2))
"
```
Expected: 打印 2 条量子位 RSS 条目, 有 title/url/desc/ts.

- [ ] **Step 3: Mark complete**

---

### Task 1.6: [AUTO] fetchers.py — fetch_article_text (Jina Reader)

**Files:**
- Modify: `~/Desktop/ai-project/hooks/ai_news/fetchers.py`
- Reference: `~/Desktop/ai-project/hooks/fetch-ai-news.py:354-371`

- [ ] **Step 1: append Jina Reader 函数到 fetchers.py**

```python
# 追加到 fetchers.py 末尾

ARTICLE_TIMEOUT = 30
ARTICLE_MAX_CHARS = 6000


def fetch_article_text(url: str) -> tuple:
    """用 Jina Reader 抓文章正文. 返回 (text, err_str).
    text 去掉图片 md / 压缩空行, 截取到 ARTICLE_MAX_CHARS."""
    if not url or not url.startswith(("http://", "https://")):
        return "", "invalid url"
    jina_url = JINA_READER_PREFIX + url
    try:
        raw = _fetch(jina_url, timeout=ARTICLE_TIMEOUT).decode("utf-8", errors="replace")
        raw = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", raw)  # 去图片
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw[:ARTICLE_MAX_CHARS].strip(), ""
    except urllib.error.HTTPError as e:
        return "", f"jina http {e.code}"
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"
```

- [ ] **Step 2: 验证**

Run:
```bash
cd ~/Desktop/ai-project/hooks && python3 -c "
from ai_news.fetchers import fetch_article_text
text, err = fetch_article_text('https://www.anthropic.com/news/claude-4-5')
print('err:', err)
print('text preview:', text[:200] if text else '(empty)')
"
```
Expected: err 为空, text 有内容 (200 字预览).

- [ ] **Step 3: Mark complete**

---

### Task 1.7: [AUTO] fetchers.py — fetch_all 聚合入口

**Files:**
- Modify: `~/Desktop/ai-project/hooks/ai_news/fetchers.py`

- [ ] **Step 1: append fetch_all() 到 fetchers.py**

```python
# 追加到 fetchers.py 末尾

# 源 id → fetcher 函数 dispatch
_TYPE_DISPATCH = {
    "hn_algolia": fetch_hn_algolia,
    "github_trending": fetch_github_trending,
    "rss": fetch_rss,
}


def fetch_one(source_id: str, fetcher_yaml: dict) -> dict:
    """对单个源执行抓取. 返回 {id, label, source_url, items, error, updated_at}."""
    t = fetcher_yaml.get("type", "")
    params = fetcher_yaml.get("params", {})
    fn = _TYPE_DISPATCH.get(t)
    if fn is None:
        return {"id": source_id, "items": [], "error": f"unknown type: {t}", "updated_at": _now_iso()}
    try:
        items = fn(params)
        return {"id": source_id, "items": items, "error": None, "updated_at": _now_iso()}
    except Exception as e:
        return {"id": source_id, "items": [], "error": f"{type(e).__name__}: {e}",
                "updated_at": _now_iso()}


def fetch_all(sources_config: list) -> list:
    """并行 (ThreadPoolExecutor) 抓取所有源.
    sources_config 每项: {id, label, source_url, fetcher: {type, params}}
    返回: [{id, label, source_url, items, error, updated_at}, ...]
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    results = {s["id"]: None for s in sources_config}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(fetch_one, s["id"], s["fetcher"]): s for s in sources_config}
        for fut in as_completed(futs):
            s = futs[fut]
            res = fut.result()
            res["label"] = s.get("label", s["id"])
            res["source_url"] = s.get("source_url", "")
            results[s["id"]] = res
    # 保持输入顺序
    return [results[s["id"]] for s in sources_config]
```

- [ ] **Step 2: Mark complete**

---

### Task 1.8: [AUTO] feedback.py — 读反馈 + get_stage + get_positives

**Files:**
- Create: `~/Desktop/ai-project/hooks/ai_news/feedback.py`
- Create: `~/Desktop/ai-project/hooks/ai_news/tests/test_feedback.py`

- [ ] **Step 1: 写测试 `tests/test_feedback.py`**

```python
import unittest
from unittest.mock import patch
from ai_news.feedback import get_stage, get_positives


class TestGetStage(unittest.TestCase):
    def test_cold_under_10(self):
        fb = {"votes": {f"u{i}": {"source": "hackernews"} for i in range(5)}}
        self.assertEqual(get_stage("hackernews", fb), "cold")

    def test_mid_10_to_50(self):
        fb = {"votes": {f"u{i}": {"source": "hackernews"} for i in range(25)}}
        self.assertEqual(get_stage("hackernews", fb), "mid")

    def test_hot_50_plus(self):
        fb = {"votes": {f"u{i}": {"source": "hackernews"} for i in range(60)}}
        self.assertEqual(get_stage("hackernews", fb), "hot")

    def test_other_source_not_counted(self):
        fb = {"votes": {f"u{i}": {"source": "github_trending"} for i in range(60)}}
        self.assertEqual(get_stage("hackernews", fb), "cold")

    def test_empty_source_not_counted(self):
        fb = {"votes": {f"u{i}": {"source": ""} for i in range(60)}}
        self.assertEqual(get_stage("hackernews", fb), "cold")


class TestGetPositives(unittest.TestCase):
    def test_returns_positives_for_source(self):
        fb = {
            "votes": {
                "url1": {"source": "hackernews", "title": "A", "ts": "2026-04-20T10:00:00+09:00"},
                "url2": {"source": "github_trending", "title": "B", "ts": "2026-04-20T11:00:00+09:00"},
                "url3": {"source": "hackernews", "title": "C", "ts": "2026-04-20T12:00:00+09:00"},
            }
        }
        out = get_positives("hackernews", fb, limit=10)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["title"], "C")  # 按 ts desc
        self.assertEqual(out[1]["title"], "A")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run 验证测试失败**

Run: `cd ~/Desktop/ai-project/hooks && python -m unittest ai_news.tests.test_feedback -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: 写 `feedback.py`**

```python
"""反馈读写 + 启动阶段判定 + few-shot 正负例构造."""
import json
import os
from typing import Optional

FEEDBACK_PATH = os.path.expanduser("~/Desktop/ai-project/data/ai-news-feedback.json")


def load_feedback() -> dict:
    """读 ai-news-feedback.json. 失败返回空 {'votes': {}}."""
    if not os.path.isfile(FEEDBACK_PATH):
        return {"votes": {}}
    try:
        with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"votes": {}}
        data.setdefault("votes", {})
        return data
    except Exception:
        return {"votes": {}}


def get_stage(source_id: str, feedback: dict) -> str:
    """按源独立判定阶段. 空 source 视为未知, 不计入任何源."""
    count = 0
    for v in feedback.get("votes", {}).values():
        vs = (v or {}).get("source", "")
        if vs == source_id:
            count += 1
    if count < 10:
        return "cold"
    if count < 50:
        return "mid"
    return "hot"


def get_positives(source_id: str, feedback: dict, limit: int = 10) -> list:
    """按 ts desc 返回该源最近 limit 条正例."""
    out = []
    for url, v in feedback.get("votes", {}).items():
        if (v or {}).get("source") != source_id:
            continue
        out.append({
            "url": url,
            "title": v.get("title", ""),
            "ts": v.get("ts", ""),
        })
    out.sort(key=lambda x: x["ts"], reverse=True)
    return out[:limit]
```

- [ ] **Step 4: Run 测试验证通过**

Run: `cd ~/Desktop/ai-project/hooks && python -m unittest ai_news.tests.test_feedback -v`
Expected: 6 tests OK

- [ ] **Step 5: Mark complete**

---

### Task 1.9: [AUTO] history.py — 历史持久化 + 按 URL 聚合

**Files:**
- Create: `~/Desktop/ai-project/hooks/ai_news/history.py`
- Modify: `~/Desktop/ai-project/hooks/ai_news/tests/test_history.py` (新建)

- [ ] **Step 1: 写测试 `tests/test_history.py`**

```python
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from ai_news import history


class TestHistoryAppendAndAggregate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl")
        self.tmp.close()
        self.path = self.tmp.name
        # Patch 模块里的 HISTORY_PATH
        self._orig_path = history.HISTORY_PATH
        history.HISTORY_PATH = self.path

    def tearDown(self):
        history.HISTORY_PATH = self._orig_path
        os.unlink(self.path)

    def test_append_items_creates_jsonl_lines(self):
        items = [
            {"source": "hackernews", "url": "u1", "title": "A", "desc": "d1"},
            {"source": "hackernews", "url": "u2", "title": "B", "desc": "d2"},
        ]
        history.append_items(items)
        with open(self.path) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 2)
        j = json.loads(lines[0])
        self.assertEqual(j["source"], "hackernews")
        self.assertEqual(j["url"], "u1")
        self.assertIn("ts", j)

    def test_aggregate_groups_by_url(self):
        now_iso = datetime.now(timezone.utc).isoformat()
        past_iso = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        # 手动写两条 u1 (ts 不同) + 一条 u2
        with open(self.path, "w") as f:
            f.write(json.dumps({"ts": past_iso, "source": "hackernews", "url": "u1", "title": "A"}) + "\n")
            f.write(json.dumps({"ts": now_iso, "source": "hackernews", "url": "u1", "title": "A"}) + "\n")
            f.write(json.dumps({"ts": now_iso, "source": "hackernews", "url": "u2", "title": "B"}) + "\n")
        agg = history.aggregate_by_url(source_id="hackernews")
        self.assertEqual(len(agg), 2)
        # u1 count=2, u2 count=1
        u1 = next(a for a in agg if a["url"] == "u1")
        u2 = next(a for a in agg if a["url"] == "u2")
        self.assertEqual(u1["count"], 2)
        self.assertEqual(u2["count"], 1)
        self.assertEqual(u1["first_ts"], past_iso)
        self.assertEqual(u1["last_ts"], now_iso)

    def test_get_negatives_excludes_voted_and_recent(self):
        now_iso = datetime.now(timezone.utc).isoformat()
        past_iso = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        recent_iso = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        with open(self.path, "w") as f:
            # voted url
            f.write(json.dumps({"ts": past_iso, "source": "hackernews", "url": "voted", "title": "v"}) + "\n")
            # recent url (不满 7 天)
            f.write(json.dumps({"ts": recent_iso, "source": "hackernews", "url": "recent", "title": "r"}) + "\n")
            # negative url (old + unvoted)
            f.write(json.dumps({"ts": past_iso, "source": "hackernews", "url": "neg1", "title": "n1"}) + "\n")
            f.write(json.dumps({"ts": past_iso, "source": "hackernews", "url": "neg1", "title": "n1"}) + "\n")

        feedback = {"votes": {"voted": {"source": "hackernews"}}}
        negs = history.get_negatives("hackernews", feedback, days=7, limit=10)
        self.assertEqual(len(negs), 1)
        self.assertEqual(negs[0]["url"], "neg1")
        self.assertEqual(negs[0]["count"], 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 写 `history.py`**

```python
"""历史持久化 (负例数据源). append-only jsonl, 查询时按 url 聚合."""
import json
import os
from datetime import datetime, timedelta, timezone

HISTORY_PATH = os.path.expanduser("~/Desktop/ai-project/data/ai-news-history.jsonl")


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
```

- [ ] **Step 3: Run 测试**

Run: `cd ~/Desktop/ai-project/hooks && python -m unittest ai_news.tests.test_history -v`
Expected: 3 tests OK

- [ ] **Step 4: Mark complete**

---

### Task 1.10: [AUTO] feedback.py — build_examples_inline (合并 history 负例)

**Files:**
- Modify: `~/Desktop/ai-project/hooks/ai_news/feedback.py`
- Modify: `~/Desktop/ai-project/hooks/ai_news/tests/test_feedback.py`

- [ ] **Step 1: append build_examples_inline 到 feedback.py**

```python
# 追加到 feedback.py 末尾

# 依赖约束 (reviewer 反馈 High #8):
# - feedback.py 只依赖 history (单向). history.py 不得反向依赖 feedback, 避免循环 import.
from ai_news import history as _history


def build_examples_inline(source_id: str, feedback: dict,
                          pos_limit: int = 10, neg_limit: int = 10) -> str:
    """现场生成 examples.md 内容 (不落盘), 直接嵌入 scorer prompt.
    中启动首次 examples.md 可能还是空的, 靠这个函数实时拼."""
    positives = get_positives(source_id, feedback, limit=pos_limit)
    negatives = _history.get_negatives(source_id, feedback, days=7, limit=neg_limit)

    lines = ["# 正例 (用户标记有帮助)"]
    if positives:
        for p in positives:
            date = (p.get("ts") or "")[:10]
            lines.append(f"- [{date}] {p.get('title', '')} — {p.get('url', '')}")
    else:
        lines.append("- (暂无)")

    lines.append("")
    lines.append("# 负例 (展示过但未点赞, >= 7 天)")
    if negatives:
        for n in negatives:
            date = (n.get("first_ts") or "")[:10]
            title = n.get("title", "")
            url = n.get("url", "")
            lines.append(f"- [{date}] {title} — {url} (曝光 {n.get('count', 1)} 次)")
    else:
        lines.append("- (暂无)")
    return "\n".join(lines)
```

- [ ] **Step 2: 追加测试到 test_feedback.py**

```python
# 追加到 test_feedback.py

class TestBuildExamplesInline(unittest.TestCase):
    def test_returns_formatted_md_string(self):
        fb = {"votes": {"url1": {"source": "hackernews", "title": "A", "ts": "2026-04-20T10:00:00+09:00"}}}
        # 用 patch 跳过 history (默认空, get_negatives 返回 [])
        with patch("ai_news.feedback._history") as mock_h:
            mock_h.get_negatives.return_value = []
            out = build_examples_inline("hackernews", fb)
        self.assertIn("正例", out)
        self.assertIn("负例", out)
        self.assertIn("[2026-04-20] A", out)
```

- [ ] **Step 3: Run 测试**

Run: `cd ~/Desktop/ai-project/hooks && python -m unittest ai_news.tests.test_feedback -v`
Expected: 7 tests OK

- [ ] **Step 4: Mark complete**

---

### Task 1.11: [AUTO] io.py — ai-news.json 原子读写

**Files:**
- Create: `~/Desktop/ai-project/hooks/ai_news/io.py`
- Create: `~/Desktop/ai-project/hooks/ai_news/tests/test_io.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_io.py
import json
import os
import tempfile
import unittest

from ai_news import io as ainews_io


class TestAiNewsJsonIO(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.tmp.close()
        self.path = self.tmp.name
        self._orig = ainews_io.AI_NEWS_PATH
        ainews_io.AI_NEWS_PATH = self.path

    def tearDown(self):
        ainews_io.AI_NEWS_PATH = self._orig
        os.unlink(self.path)

    def test_write_and_read_roundtrip(self):
        payload = {"updated_at": "2026-04-20T10:00:00Z", "sources": [{"id": "hackernews"}]}
        ainews_io.write_ai_news_atomic(payload)
        got = ainews_io.read_ai_news()
        self.assertEqual(got["updated_at"], payload["updated_at"])
        self.assertEqual(got["sources"][0]["id"], "hackernews")

    def test_read_missing_returns_none(self):
        os.unlink(self.path)
        self.assertIsNone(ainews_io.read_ai_news())

    def test_atomic_write_no_tmp_leftover(self):
        ainews_io.write_ai_news_atomic({"version": 2})
        self.assertFalse(os.path.exists(self.path + ".tmp"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 写 `io.py`**

```python
"""读写 ai-news.json (原子 rename) + source.md / examples.md IO helpers."""
import json
import os
from typing import Optional

AI_NEWS_PATH = os.path.expanduser("~/Desktop/ai-project/data/ai-news.json")


def read_ai_news() -> Optional[dict]:
    if not os.path.isfile(AI_NEWS_PATH):
        return None
    try:
        with open(AI_NEWS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_ai_news_atomic(payload: dict):
    os.makedirs(os.path.dirname(AI_NEWS_PATH), exist_ok=True)
    tmp = AI_NEWS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, AI_NEWS_PATH)


def read_source_md(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_source_md_atomic(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)
```

- [ ] **Step 3: Run 测试**

Run: `cd ~/Desktop/ai-project/hooks && python -m unittest ai_news.tests.test_io -v`
Expected: 3 tests OK

- [ ] **Step 4: Mark complete**

---

### Task 1.12: [AUTO] evolve.py — 备份 + diff log

**Files:**
- Create: `~/Desktop/ai-project/hooks/ai_news/evolve.py`
- Create: `~/Desktop/ai-project/hooks/ai_news/tests/test_evolve.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_evolve.py
import json
import os
import shutil
import tempfile
import unittest

from ai_news import evolve


class TestEvolveHelpers(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.source_md_path = os.path.join(self.tmpdir, "source.md")
        self.log_path = os.path.join(self.tmpdir, "evolve-log.jsonl")
        with open(self.source_md_path, "w") as f:
            f.write("---\nevolve_count: 3\n---\nbody")
        self._orig = evolve.EVOLVE_LOG_PATH
        evolve.EVOLVE_LOG_PATH = self.log_path

    def tearDown(self):
        evolve.EVOLVE_LOG_PATH = self._orig
        shutil.rmtree(self.tmpdir)

    def test_backup_creates_versioned_copy(self):
        backup = evolve.backup_source(self.source_md_path, evolve_count=3)
        self.assertTrue(os.path.isfile(backup))
        self.assertTrue(backup.endswith(".v3"))
        with open(backup) as f:
            self.assertIn("evolve_count: 3", f.read())

    def test_load_frontmatter_parses_count(self):
        fm = evolve.load_frontmatter(self.source_md_path)
        self.assertEqual(fm.get("evolve_count"), 3)

    def test_write_evolve_log_appends_jsonl(self):
        evolve.write_evolve_log({"source": "hackernews", "from": 3, "to": 4, "diff": "..."})
        with open(self.log_path) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 1)
        j = json.loads(lines[0])
        self.assertEqual(j["source"], "hackernews")
        self.assertIn("ts", j)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 写 `evolve.py`**

```python
"""evolve 辅助: 备份 source.md.v{N} + 写 diff log.
实际的 AI 重写工作由 evolve-source-preferences subagent 做, 这里只管工程层面."""
import json
import os
import shutil
from datetime import datetime, timezone

EVOLVE_LOG_PATH = os.path.expanduser("~/Desktop/ai-project/data/ai-news-evolve-log.jsonl")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_frontmatter(source_md_path: str) -> dict:
    """解析 source.md 的 YAML frontmatter (--- ... ---). 返回 dict, 失败返回空."""
    if not os.path.isfile(source_md_path):
        return {}
    out = {}
    with open(source_md_path, "r", encoding="utf-8") as f:
        content = f.read()
    if not content.startswith("---"):
        return {}
    try:
        end = content.index("\n---", 3)
        fm_text = content[3:end]
    except ValueError:
        return {}
    for line in fm_text.strip().splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip().strip('"\'')
        # 简易类型推断: int / bool / str
        if v.isdigit():
            out[k] = int(v)
        elif v.lower() in ("true", "false"):
            out[k] = v.lower() == "true"
        else:
            out[k] = v
    return out


def backup_source(source_md_path: str, evolve_count: int) -> str:
    """cp source.md → source.md.v{evolve_count}. 返回备份路径."""
    backup = f"{source_md_path}.v{evolve_count}"
    shutil.copy2(source_md_path, backup)
    return backup


def write_evolve_log(entry: dict):
    """追加一行 jsonl log. entry 至少含 source / from / to."""
    os.makedirs(os.path.dirname(EVOLVE_LOG_PATH), exist_ok=True)
    entry.setdefault("ts", _now_iso())
    with open(EVOLVE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

- [ ] **Step 3: Run 测试**

Run: `cd ~/Desktop/ai-project/hooks && python -m unittest ai_news.tests.test_evolve -v`
Expected: 3 tests OK

- [ ] **Step 4: Mark complete**

---

### Task 1.13: [AUTO] 全量 Chunk 1 测试 + fetch-ai-news.py 重写 (不冒烟, 冒烟在 Task 3.5)

**Files:**
- Modify: `~/Desktop/ai-project/hooks/fetch-ai-news.py` (降级为抓取 debug 入口)

**注意** (reviewer 反馈 High #4): 真正的抓取冒烟放在 Task 3.5 (Chunk 3 完成 source.md/examples.md 后). 本任务只做: 单测 + 写脚本 + 语法校验. **不**执行脚本.

- [ ] **Step 1: 跑全部 Chunk 1 单测**

Run: `cd ~/Desktop/ai-project/hooks && python -m unittest discover ai_news/tests -v`
Expected: 所有测试 OK (约 20 个)

- [ ] **Step 2: 重写 `fetch-ai-news.py`** (删掉原 534 行, 换成薄 wrapper)

```python
#!/usr/bin/env python3
"""AI 大事抓取层 debug 入口 (v2).

只跑 fetchers + filters, 不跑 scorer / summary / analysis.
输出每源原始抓取结果到 /tmp/ai-news-raw-{source_id}.json, 供调 fetcher.yaml 参数时看.

Pipeline 完整流程由 /loop 主 agent 通过 ai-news-fetch skill 驱动, 不走这个脚本.
"""
import json
import os
import sys
import yaml  # 注意: 用户环境如无 yaml, 改用简易解析或加装
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ai_news.fetchers import fetch_one
from ai_news.filters import apply_hard_filter

SOURCES_DIR = Path.home() / ".claude" / "skills" / "ai-news-filter" / "sources"
OUT_TPL = "/tmp/ai-news-raw-{}.json"

SOURCE_IDS = ["hackernews", "github_trending", "qbitai", "ithome_tw"]


def load_fetcher_yaml(source_id: str) -> dict:
    path = SOURCES_DIR / source_id / "fetcher.yaml"
    if not path.is_file():
        return {"type": "", "params": {}}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main():
    for sid in SOURCE_IDS:
        cfg = load_fetcher_yaml(sid)
        res = fetch_one(sid, cfg)
        # 硬规则过滤
        if res.get("items"):
            filtered = apply_hard_filter(res["items"])
            res["items_before_hard_filter"] = len(res["items"])
            res["items"] = filtered
        out_path = OUT_TPL.format(sid)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        print(f"[{sid}] {len(res.get('items', []))} items → {out_path} "
              f"(err: {res.get('error') or '-'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

yaml 模块在 Task 1.1 Step 1 已强制装好, 这里不再校验.

- [ ] **Step 3: 验证脚本语法** (不执行)

Run: `python3 -c "import ast; ast.parse(open('/Users/augus/.claude/hooks/fetch-ai-news.py').read())"`
Expected: 无输出 (解析成功). **不执行脚本** — 执行需要 sources/<id>/source.md (Chunk 3) 和网络, 冒烟在 Task 3.5.

- [ ] **Step 4: Mark complete**

---

## Chunk 2: 架构根基验证 + Subagent 契约 + Skill 骨架

**范围**: 先做**两个架构根基 smoke test** (Task 2.0a/2.0b, 前置自 Chunk 5), 确认 subagent model 覆盖 + Agent tool 并发上限. 这两项决定整个 plan 是否跑得起来. 通过后再写 4 个 subagent md + ai-news-fetch/SKILL.md + ai-news-filter/reference/*.md.

**执行约束 (reviewer 反馈 High #7)**:
- **Task 2.0a 必须最先跑**. 若 subagent model 不被覆盖 (主 agent Sonnet 跑了 Haiku 费用), 整个架构推倒, 改用 `subprocess.run(["claude", "-p", ...])` 路径.
- **Task 2.0b 决定并发数**. 若实测 < 10, 要回头改 Chunk 3-4 的"分批"并发度.

**所有 task** `[AUTO]` (写文件), **Task 2.0a/2.0b/2.7 `[MANUAL]`** (交互式 Claude Code 验证).

**文件结构**:
```
~/Desktop/ai-project/.claude/agents/
├── news-scorer.md
├── news-summary.md
├── news-analysis.md
└── evolve-source-preferences.md

~/Desktop/ai-project/.claude/skills/ai-news-fetch/SKILL.md

~/Desktop/ai-project/.claude/skills/ai-news-filter/reference/
├── scoring-criteria.md
├── feedback-evolution.md
└── cold-start-strategy.md
```

---

### Task 2.0a: [MANUAL] 架构根基 smoke — subagent model 覆盖验证 (前置自 Chunk 5)

**目的**: 确认主 agent 是 Sonnet 时, 派的 subagent (Haiku/Opus) 真的按 subagent md 里 `model:` 跑, 不是继承主 agent 模型. **若此步失败, 整个 spec §4 + §9 架构作废, 需改用 subprocess 路径**.

- [ ] **Step 1: 先完成 Task 2.1 (临时) — 仅为这次验证, 写 news-scorer.md**

(为了跑这个测试, 先 preemptively 建 news-scorer.md. 若后续 Task 2.1 需要改, 再改.)

```bash
mkdir -p ~/Desktop/ai-project/.claude/agents
cat > ~/Desktop/ai-project/.claude/agents/news-scorer.md <<'EOF'
---
name: news-scorer
description: 测试用
model: claude-haiku-4-5
tools: Read, Write
---

# 评分员 (smoke test)

收到 prompt 后打印 "hello from news-scorer", 然后 Write /tmp/scorer-probe.json 内容 `{"ok": true}`.
EOF
```

- [ ] **Step 2: tmux 启动 Sonnet Claude Code 会话**

```bash
tmux new -s ai-news-smoke
claude --model sonnet
```

- [ ] **Step 3: 派 news-scorer (haiku) 并观察账单**

在 Claude Code 里:
```
使用 Agent tool 派 news-scorer, prompt: "hello"
subagent_type: news-scorer
```

- [ ] **Step 4: 检查 Anthropic dashboard / API 用量**

期望: 那次 subagent 调用的 token 消耗按 **Haiku 价** (input $0.8/MTok, 而不是 Sonnet $3/MTok).

- [ ] **Step 5: 若 subagent 被按 Sonnet 跑 (model 不被覆盖)**

Spec §4 假设失败. 记录到 `~/Desktop/ai-news-v2-smoke-notes.md`:
```
- [FAIL] subagent model 覆盖: 主 agent Sonnet 派 haiku subagent 被按 Sonnet 计费
- 决策: 放弃 Agent tool 路径, 改用 subprocess.run(["claude", "-p", prompt, "--model", model]).
- 影响: ai-news-fetch/SKILL.md 重写, 不再派 subagent, 改为主 agent 调 Python 函数 subprocess.
```

**plan 后续任务部分报废, 需要重新设计**. 暂停, 向用户报告.

- [ ] **Step 6: 若 subagent 按 Haiku 跑 (model 覆盖成功)**

记录到 smoke-notes: `[PASS] subagent model 覆盖成功`. 继续 Task 2.0b.

- [ ] **Step 7: Mark complete**

---

### Task 2.0b: [MANUAL] 架构根基 smoke — Agent tool 并发上限

**目的**: 主 agent 一次 message 内能并发派几个 Agent tool call? Spec §3 假设 10 (summary 批次), 实测.

- [ ] **Step 1: 准备 10 个 dummy news-summary 输入**

(news-summary.md 也 preemptively 建一下, 同 Task 2.0a 方式)

```bash
cat > ~/Desktop/ai-project/.claude/agents/news-summary.md <<'EOF'
---
name: news-summary
description: 测试用
model: claude-haiku-4-5
tools: Write
---

# 摘要员 (smoke test)

收到 prompt 后 Write 对应 output_path, 内容 `{"summary": "probe", "warning": ""}`.
EOF
```

- [ ] **Step 2: 在 Claude Code 会话里一次 message 派 10 个 summary**

```
在一条 message 里发 10 个 Agent tool call, 每个派 news-summary,
prompt 分别指向 /tmp/ai-news-summary-dummy-{1..10}.json (各写 title=dummy-N url=https://example.com/N)
```

- [ ] **Step 3: 观察是否都成功返回**

- 全 10 个都成功: spec §3 "10 并发" 成立, Chunk 3-4 的分批并发度保持 10.
- 最多 N 个 (N < 10): 更新 ai-news-fetch/SKILL.md §2.4 的并发度, 批次数变为 `ceil(40/N)`. 记录到 smoke-notes.

- [ ] **Step 4: Mark complete**

---

### Task 2.1: [AUTO] ~/Desktop/ai-project/.claude/agents/news-scorer.md

**Files:**
- Create: `~/Desktop/ai-project/.claude/agents/news-scorer.md`
- Reference: spec §9.1

- [ ] **Step 1: 建目录**

```bash
mkdir -p ~/Desktop/ai-project/.claude/agents
```

- [ ] **Step 2: 写文件** (完整内容见 spec §9.1, 复制过去)

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
\`\`\`json
{
  "source_id": "hackernews",
  "stage": "cold" | "mid" | "hot",
  "source_md": "<source.md 内容完整字符串>",
  "examples_md": "<examples.md 内容, 可能是空字符串>",
  "candidates": [{"title":"...","url":"...","desc":"...","score":243,"comments":87}]
}
\`\`\`

## 步骤
1. Read input_path 获取所有输入
2. 若 `stage == "cold"`, 返回错误: 冷启动不应调用 scorer
3. 按 source_md 偏好 + examples few-shot, 对 candidates 每条给 0-10 分 + ≤ 25 字 reason
4. 按 ai_score desc 取前 N (N = min(10, score >= 5 的数量))
5. Write output_path 写 JSON: `{"source_id":"hackernews","items":[{"url","title","ai_score","reason"}, ...]}`
6. 返回一句话确认: "scored {N} items to {output_path}"

## 规则
- 候选少于 10 条返回实际数量, 不凑数
- reason 要具体, 不能只说"相关/不相关"
- reason 用中文, 直接说事实(例如"开源 agent 框架发布, 作者是 Anthropic")
```

- [ ] **Step 3: 验证**

Run: `cat ~/Desktop/ai-project/.claude/agents/news-scorer.md | head -5`
Expected: frontmatter 含 model + tools 行.

- [ ] **Step 4: Mark complete**

---

### Task 2.2: [AUTO] ~/Desktop/ai-project/.claude/agents/news-summary.md

**Files:**
- Create: `~/Desktop/ai-project/.claude/agents/news-summary.md`
- Reference: spec §9.2

- [ ] **Step 1: 写文件**

```markdown
---
name: news-summary
description: 对新闻单条生成 50-80 字中文摘要
model: claude-haiku-4-5
tools: WebFetch, Write
---

# 摘要员指令

主 agent 派遣你时 prompt 给出 `title`, `url`, `output_path`.

## 步骤
1. 用 WebFetch 抓 `https://r.jina.ai/{url}` 获取正文 (Jina Reader)
2. 生成 50-80 字中文摘要, 只写结论不铺垫, 不 markdown/引号/前后缀
3. Write output_path: `{"summary":"...","warning":""}`, 抓取失败时 `warning: "jina_failed"`, summary 仅凭 title 生成
4. 返回确认: "summary written to {output_path}"

## 规则
- 摘要不超过 80 字, 不少于 50 字
- 不带表情符号/markdown 标题/代码块
```

- [ ] **Step 2: Mark complete**

---

### Task 2.3: [AUTO] ~/Desktop/ai-project/.claude/agents/news-analysis.md

**Files:**
- Create: `~/Desktop/ai-project/.claude/agents/news-analysis.md`
- Reference: spec §9.3

- [ ] **Step 1: 写文件**

```markdown
---
name: news-analysis
description: 分析新闻对当前工作区 + Claude 使用的帮助
model: claude-opus-4-7
tools: Read, WebFetch, Write
---

# 分析员指令

主 agent 派遣你时 prompt 给出 `title`, `url`, `workspace_context_path`, `output_path`.

## 步骤
1. Read workspace_context_path (CLAUDE.md) 了解工作区技术栈
2. WebFetch 抓正文 `https://r.jina.ai/{url}`
3. 生成两维度分析:
   - `workspace_help`: 一句话 30-60字, 或 "无相关"
   - `claude_usage`: 一句话 30-60字, 或 "无相关"
4. Write output_path: `{"workspace_help":"...","claude_usage":"...","warning":""}`
5. 返回确认

## 规则
- workspace_help 必须具体到工作区技术栈 (Flutter / Go Kratos / Lua), 不能泛泛 "对开发有帮助"
- claude_usage 关注: 新 skill, plugin, prompt 技巧, 模型能力变化, 工作流改进
- 两者都无关就都写"无相关"
```

- [ ] **Step 2: Mark complete**

---

### Task 2.4: [AUTO] ~/Desktop/ai-project/.claude/agents/evolve-source-preferences.md

**Files:**
- Create: `~/Desktop/ai-project/.claude/agents/evolve-source-preferences.md`
- Reference: spec §9.4

- [ ] **Step 1: 写文件**

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
\`\`\`json
{
  "source_md_current": "<source.md 完整内容>",
  "source_md_path": "/Users/augus/.claude/skills/ai-news-filter/sources/<id>/source.md",
  "positives": [{"title":"...","url":"...","desc":"..."}, ...],
  "negatives": [...],
  "evolve_count_new": 4,
  "examples_md_path": "/.../examples.md"
}
\`\`\`

## 步骤
1. Read input_path 获取所有输入
2. 分析 positives / negatives 共同特征 (高频关键词 / 主题 / 作者 / 来源模式)
3. 重写三段:
   - 「核心判断维度」(保留人类初稿意图 + 融合反馈)
   - 「用户正例特征」
   - 「用户负例特征」
4. frontmatter 更新:
   - `evolve_count`: `evolve_count_new`
   - `last_evolve_at`: 现在 ISO 时间
   - `updated_by`: `evolve_v{evolve_count_new}`
5. Write source_md_path: 写入整个新 source.md
6. Write examples_md_path: 按 下面格式刷新 examples.md (正例 + 负例最新数据)
7. Write output_path: `{"evolved":true,"evolve_count_new":4,"diff_summary":"..."}`

examples.md 格式:
\`\`\`
# 正例 (用户标记有帮助)
- [YYYY-MM-DD] {title} — {url}
- ...

# 负例 (展示过但未点赞, >= 7 天)
- [YYYY-MM-DD] {title} — {url} (曝光 X 次)
- ...
\`\`\`

## 规则
- 保留 frontmatter 所有其他字段 (source_id / label 等)
- 「核心判断维度」不能完全丢弃人类初稿意图, 在其基础上增强
- 不要加偏激判断 (如"只看开源"), 保持多样性
- 若 positives / negatives 都少 (< 5 条), 返回 `{"evolved": false, "reason": "data_insufficient"}`, 不改文件
```

- [ ] **Step 2: Mark complete**

---

### Task 2.5: [AUTO] ai-news-filter/reference/*.md

**Files:**
- Create: `~/Desktop/ai-project/.claude/skills/ai-news-filter/reference/scoring-criteria.md`
- Create: `~/Desktop/ai-project/.claude/skills/ai-news-filter/reference/feedback-evolution.md`
- Create: `~/Desktop/ai-project/.claude/skills/ai-news-filter/reference/cold-start-strategy.md`

- [ ] **Step 1: 建目录**

```bash
mkdir -p ~/Desktop/ai-project/.claude/skills/ai-news-filter/reference
mkdir -p ~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/{hackernews,github_trending,qbitai,ithome_tw}
```

- [ ] **Step 2: 写 `scoring-criteria.md`**

```markdown
# 通用打分准则

所有 source 共享的基础规则. 具体源偏好在 `sources/<id>/source.md`.

## 0-10 分段

- 9-10: 强相关 + 质量信号强 (开源重要项目首发, 官方 release, 技术深度文章)
- 7-8: 相关 + 质量中 (实用工具, 技术对比, 技术综述)
- 5-6: 弱相关 (沾边但不深, benchmark 数据, 业内动态)
- 3-4: 不相关但不剔除 (用户的 source 偏好可能后续学到)
- 0-2: 明显噪音 (硬规则没拦住的漏网之鱼)

## reason 规则

- 具体到事实 + 关键词
- 不要空泛 ("相关", "有用")
- 如果依据是用户历史反馈 (few-shot), 说"与历史偏好 XXX 匹配"
- ≤ 25 字

## 平票处理

score 相同的条目按源原生排序 tiebreak (HN 按 points, GH 按 today_stars_int, RSS 按 pubDate).
```

- [ ] **Step 3: 写 `feedback-evolution.md`**

```markdown
# Evolve 规则

只对热启动源 (feedback ≥ 50 条) 跑.

## 触发条件

距上次 evolve 该源新增反馈 ≥ 20 条 (不是累计, 是增量).

## Evolve 步骤

由主 agent 按以下顺序跑:

1. Python: 读 source.md frontmatter `evolve_count` (= N)
2. Python: `cp source.md source.md.v{N}` 备份
3. Python: 组装 evolve subagent 输入 JSON (positives / negatives 最近各 30 条, evolve_count_new=N+1)
4. 派 evolve-source-preferences subagent (Opus 4.7)
5. subagent 返回后, 主 agent 记 diff 到 `ai-news-evolve-log.jsonl`
6. 发 TG 通知 evolve 已完成

## 手动回滚

用户观察到 evolve 后质量下降, 自行 `cp source.md.v{N-1} source.md`.

## 非自动回滚说明 (v1 不做)

v1 不自动监控点赞率 + 回滚. 这部分留给 v2 未来扩展.
```

- [ ] **Step 4: 写 `cold-start-strategy.md`**

```markdown
# 冷/中/热启动策略

按源独立统计反馈数, 每源可能处于不同阶段.

## 冷启动 (< 10 条反馈)

- 不派 scorer subagent (会瞎编)
- 硬规则过滤后按源原生排序, 取 Top N (N = min(10, 实际数量))
  - HN: score (HN points) desc
  - GitHub: today_stars_int desc
  - RSS: pubDate desc
- stage 写 "cold" 到 ai-news.json

## 中启动 (10-50 条)

- 派 scorer subagent
- Few-shot: 正负各 10 条
- examples.md 若是空, 主 agent **现场从 feedback + history 拼一份**嵌入 scorer 输入, 不读文件 (见 §8.2 build_examples_inline)
- Top N = min(10, ai_score >= 5 的数量), 平票按原生排序

## 热启动 (≥ 50 条)

- 同中启动 scorer
- Few-shot 加到正负各 20-30 条
- 额外: pipeline 跑完后检查 evolve 条件

## Top N 是上限

某源可能只有 4 条通过, 就展示 4 条. TG 通知动态显示.
```

- [ ] **Step 5: Mark complete**

---

### Task 2.6: [AUTO] ~/Desktop/ai-project/.claude/skills/ai-news-fetch/SKILL.md

**Files:**
- Create: `~/Desktop/ai-project/.claude/skills/ai-news-fetch/SKILL.md`
- Reference: spec §3 架构图 + §5 时间算法

这是 /loop 每次唤醒读的入口, **最关键的文件**. 包含:
- /loop 时间算法
- Pipeline 编排顺序
- subagent 派遣模板 (Agent tool 调用形式)
- 错误降级规则

- [ ] **Step 1: 建目录**

```bash
mkdir -p ~/Desktop/ai-project/.claude/skills/ai-news-fetch
```

- [ ] **Step 2: 写文件**

```markdown
---
name: ai-news-fetch
description: AI 大事每日自动抓取 + 评分 + 摘要 + 分析 + 写入 + TG 通知. /loop 每次唤醒调用.
---

# AI 大事 v2 主编排

## 适用场景

**Only** 通过 `/loop` 动态模式调用. 每次唤醒都执行 `on_wakeup` 流程.

## on_wakeup 流程

### 步骤 1: 判断是否到 10:00 窗口

```python
now = datetime.now(LOCAL_TZ)
if now.hour == 10 and now.minute < 30:
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

本地时区请在首次运行时校准 (开放问题 §20.1).

### 步骤 2: run_full_pipeline 编排

#### 2.1 抓取层 (subprocess Python, 不用 AI)

```bash
python3 -c "
import sys, json
sys.path.insert(0, '/Users/augus/.claude/hooks')
from ai_news.fetchers import fetch_one
from ai_news.filters import apply_hard_filter
from pathlib import Path
import yaml

SOURCES = ['hackernews', 'github_trending', 'qbitai', 'ithome_tw']
BASE = Path.home() / '.claude' / 'skills' / 'ai-news-filter' / 'sources'
out = []
for sid in SOURCES:
    cfg = yaml.safe_load(open(BASE / sid / 'fetcher.yaml'))
    r = fetch_one(sid, cfg)
    if r.get('items'):
        r['items'] = apply_hard_filter(r['items'])
    out.append(r)
import json
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

```python
from ai_news.io import write_ai_news_atomic
from ai_news.history import append_items

# 主列表已组装完成, 格式见 spec §10
write_ai_news_atomic(payload)
append_items([{"source": ..., "url": ..., "title": ..., "desc": ...} for ... in payload])
```

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
   - 派 evolve-source-preferences subagent
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
```

- [ ] **Step 3: Mark complete**

---

### Task 2.7: [MANUAL] Subagent 冒烟 (人工触发)

**Files:** 无写入, 只验证.

- [ ] **Step 1: 在 Claude Code 会话里手工派 news-scorer 一次**

先手工建一个模拟 input:
```bash
cat > /tmp/ai-news-scorer-test.json <<'EOF'
{
  "source_id": "hackernews",
  "stage": "mid",
  "source_md": "# HN 评分偏好\n\n## 核心判断维度\n- 开源 agent/MCP 类优先\n",
  "examples_md": "# 正例\n- [2026-04-15] Anthropic Sonnet 4.6 release — https://x.com\n# 负例\n- (暂无)",
  "candidates": [
    {"title": "Show HN: An open-source MCP server for Postgres", "url": "https://example.com/1", "desc": "A new MCP server", "score": 200, "comments": 80},
    {"title": "Google Q4 earnings beats estimates", "url": "https://example.com/2", "desc": "Stock up", "score": 50, "comments": 20},
    {"title": "New Claude agent framework benchmark", "url": "https://example.com/3", "desc": "100+ tools", "score": 150, "comments": 60}
  ]
}
EOF
```

在 Claude Code 里 (新开一个 session) 输入:
```
使用 Agent tool 派一个 news-scorer subagent,
prompt: "你是 news-scorer. 读 /tmp/ai-news-scorer-test.json, 打分后写 /tmp/ai-news-scored-test.json"
subagent_type: news-scorer
```

- [ ] **Step 2: 检查输出**

```bash
cat /tmp/ai-news-scored-test.json
```

Expected: JSON 格式, `items` 数组 3 条, 每条有 `ai_score` (0-10) 和 `reason` (中文短句), 按 ai_score desc. 第一条应该是 MCP/framework 类 (根据 source.md 偏好).

- [ ] **Step 3: 若输出不符合, 按排障矩阵定位**

| 现象 | 可能原因 | 修法 |
|---|---|---|
| subagent 没有被派遣 | subagent_type 名字错, 或 agents/news-scorer.md 不存在 | `ls ~/Desktop/ai-project/.claude/agents/news-scorer.md`, 检查 `name:` frontmatter |
| subagent 跑了但按 Sonnet 计费 | model 覆盖失败 (已在 Task 2.0a 验证过 — 若那时是 PASS, 此处重新跑应仍 PASS) | 重跑 Task 2.0a 确认; 若突然退化, 可能 Claude Code 更新导致行为变化, 向 Anthropic 反馈 |
| output JSON 格式错 (缺字段 / 多字段) | SKILL.md 里 output schema 描述不清 | 改 news-scorer.md, 明示"Write 必须含 items 字段 + 每项含 url/title/ai_score/reason" |
| output JSON valid 但 ai_score 全是 0 或 10 | few-shot 示例给得太极端, 或 source.md 偏好描述太片面 | 改 /tmp/ai-news-scorer-test.json 的 source_md / examples_md, 或调 news-scorer.md 的打分指导 |
| reason 是空 / 太笼统 "相关" | news-scorer.md 规则不够严格 | 在 news-scorer.md ## 规则 段加"reason 必须提到具体关键词或用户历史偏好" |
| subagent Read 失败 | tools 白名单漏了 Read | 检查 frontmatter `tools: Read, Write` 完整 |
| subagent Write 失败 | tools 白名单漏了 Write | 同上 |

- [ ] **Step 4: 同理冒烟 news-summary (Haiku)**

- prompt 直接嵌: `"你是 news-summary. title: 'Anthropic 发布 Claude 4.7' url: 'https://anthropic.com/news/claude-4-7' 写摘要到 /tmp/ai-news-summary-probe.json"`
- 检查输出: `cat /tmp/ai-news-summary-probe.json` → `{"summary":"...","warning":""}`, summary 50-80 字中文.

排障: 抓取失败看 `warning: "jina_failed"` 字段, 并检查 `https://r.jina.ai/<url>` 是否可访问.

- [ ] **Step 5: 同理冒烟 news-analysis (Opus)**

- prompt 嵌: `"你是 news-analysis. title: '...' url: '...' workspace_context_path: '/Users/augus/Desktop/开发项目/live_app/CLAUDE.md' 写分析到 /tmp/ai-news-analysis-probe.json"`
- 检查输出: `{"workspace_help": "...", "claude_usage": "...", "warning": ""}`, 每字段 30-60 字或 "无相关".

排障: workspace_help 太笼统 → 调 news-analysis.md "## 规则 - workspace_help 必须具体到工作区技术栈".

- [ ] **Step 6: Mark complete**

---

## Chunk 3: 每源 source.md / examples.md 初值 + 抓取冒烟

**范围**: 4 个 `sources/<id>/{source.md, examples.md}` 初值 (fetcher.yaml 已在 Chunk 1 Task 1.1 前置) + Task 3.5 抓取冒烟.

**任务标签**:
- Task 3.1-3.4 `[AUTO]` (写文件)
- Task 3.5 `[MANUAL]` (需要外网 HN/GitHub/RSS, 实际跑脚本, 非离线可验)

---

### Task 3.1: [AUTO] sources/hackernews/ (fetcher.yaml 已在 Chunk 1 Task 1.1 前置)

**Files:**
- Create: `~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/hackernews/source.md`
- Create: `~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/hackernews/examples.md`

- [ ] **Step 1: 写 source.md**

```markdown
---
source_id: hackernews
label: Hacker News
updated_by: cold_start
last_evolve_at: ""
evolve_count: 0
---

# HN 评分偏好

## 核心判断维度
(人类初稿, evolve 后会被重写)
- HN 的价值在讨论热度 >= 单纯 score, 评论数 100+ 的优先
- 优先: 开源 agent/框架发布, MCP 类工具, 技术深度文章, 作者历史高质量
- 次优: benchmark 对比, 技术综述, 官方 release 说明
- 扣分: 已被硬规则漏过的融资/产业/政策/硬件业
- "Show HN" 类型若是完整开源项目加分, 若是 wip demo 减分

## 用户正例特征 (evolve 自动提取, 冷启动为空)
- 高频关键词: (evolve 填充)
- 偏好模式: (evolve 填充)

## 用户负例特征 (evolve 自动提取, 冷启动为空)
- 低频但曾出现: (evolve 填充)
- 被跳过模式: (evolve 填充)
```

- [ ] **Step 2: 写 examples.md** (冷启动空占位)

```markdown
# 正例 (用户标记有帮助)
- (暂无)

# 负例 (展示过但未点赞, >= 7 天)
- (暂无)
```

- [ ] **Step 3: Mark complete**

---

### Task 3.2: [AUTO] sources/github_trending/ (fetcher.yaml 已前置)

**Files:**
- Create: `~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/github_trending/source.md`
- Create: `~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/github_trending/examples.md`

- [ ] **Step 1: 写 source.md**

```markdown
---
source_id: github_trending
label: GitHub Trending
updated_by: cold_start
last_evolve_at: ""
evolve_count: 0
---

# GitHub Trending 评分偏好

## 核心判断维度
- 优先: AI/LLM/agent framework, MCP 服务端, 生产级工具, 有明确 README 的完整项目
- 次优: 官方 SDK, wrapper, example repo
- 扣分: awesome-list, tutorial-only, README 仅截图无说明, clone 某知名项目改名
- 语言偏好: TypeScript / Python / Rust 为主, 其他语言看是否是 AI 相关

## 用户正例特征 (evolve 自动提取, 冷启动为空)
## 用户负例特征 (evolve 自动提取, 冷启动为空)
```

- [ ] **Step 2: 写 examples.md** (同 Task 3.1 空占位)

- [ ] **Step 3: Mark complete**

---

### Task 3.3: [AUTO] sources/qbitai/ (fetcher.yaml 已前置)

**Files:**
- Create: `~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/qbitai/source.md`
- Create: `~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/qbitai/examples.md`

- [ ] **Step 1: 写 source.md**

```markdown
---
source_id: qbitai
label: 量子位
updated_by: cold_start
last_evolve_at: ""
evolve_count: 0
---

# 量子位评分偏好

## 核心判断维度
- 优先: 国内外大模型 / 新产品首发 / AI 芯片技术突破 / 顶会论文解读
- 次优: 行业动态, 团队变化, benchmark 数据
- 扣分: 融资/并购类 (硬规则一般会拦, 但有时漏), 明显是 PR 稿的推广文
- 作者信号: 量子位自家记者的深度稿 > 转载稿

## 用户正例特征 (evolve 自动提取, 冷启动为空)
## 用户负例特征 (evolve 自动提取, 冷启动为空)
```

- [ ] **Step 2: 写 examples.md** (空占位)

- [ ] **Step 3: Mark complete**

---

### Task 3.4: [AUTO] sources/ithome_tw/ (fetcher.yaml 已前置)

**Files:**
- Create: `~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/ithome_tw/source.md`
- Create: `~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/ithome_tw/examples.md`

- [ ] **Step 1: 写 source.md**

```markdown
---
source_id: ithome_tw
label: iThome (台湾)
updated_by: cold_start
last_evolve_at: ""
evolve_count: 0
---

# iThome (台湾) 评分偏好

## 核心判断维度
- 优先: 国际大厂 AI 新功能发布 (OpenAI/Anthropic/Google/Microsoft/Meta), 开源项目评测
- 次优: 台湾本地企业 AI 应用, 技术议题解析
- 扣分: 资安漏洞/攻击 (硬规则会拦), ESG/永续/政策 (硬规则), 晶片代工产业链 (硬规则)
- 中文繁体呈现, 原文风格偏技术新闻专业

## 用户正例特征 (evolve 自动提取, 冷启动为空)
## 用户负例特征 (evolve 自动提取, 冷启动为空)
```

- [ ] **Step 2: 写 examples.md** (空占位)

- [ ] **Step 3: Mark complete**

---

### Task 3.5: [MANUAL] 抓取层冒烟 (fetch-ai-news.py) — 合并 Task 1.13 Step 2

**Files:** 无写入, 验证抓取.

- [ ] **Step 1: 跑 fetch-ai-news.py**

Run: `python3 ~/Desktop/ai-project/hooks/fetch-ai-news.py`
Expected: 打印 4 行, 每行像 `[hackernews] N items → /tmp/ai-news-raw-hackernews.json (err: -)`. items 数量 > 0.

- [ ] **Step 2: 检查 /tmp 输出**

```bash
ls -la /tmp/ai-news-raw-*.json
for f in /tmp/ai-news-raw-*.json; do
  echo "=== $f ==="
  python3 -c "import json; d=json.load(open('$f')); print(f\"items: {len(d.get('items', []))}, err: {d.get('error', '-')}\")"
done
```
Expected: 每源 10+ items (github_trending 可能少), error 为 null.

- [ ] **Step 3: 若某源 error, 排查**

- hackernews error: 检查网络 / HN Algolia 服务
- github_trending error: 检查 HTML 结构 (GitHub 可能改 DOM)
- qbitai / ithome error: 检查 RSS 有效性

- [ ] **Step 4: Mark complete**

---

## Chunk 4: Dashboard 改动

**范围**: 3 个 Dashboard 文件 (`usage-web.py` / `usage_web_render.py` / `usage-web.js`).

**所有任务** `[AUTO]` (写代码), **最后一个 `[MANUAL]`** (浏览器验证).

---

### Task 4.1: [AUTO] 删除 /news/refresh 后端路由

**Files:**
- Modify: `~/Desktop/ai-project/hooks/usage-web.py:240-277` (删除 /news/refresh 相关分支)

- [ ] **Step 1: 读当前代码**

Run: `grep -n "/news/refresh\|news/refresh" ~/Desktop/ai-project/hooks/usage-web.py`
Expected: 路由检查行 + 处理分支行 (约 5-10 行)

- [ ] **Step 2: 删除路由**

修改 line ~241: `if u.path not in ("/archive", "/restore", "/clear-summary-cache", "/news/refresh", "/news/vote"):` 去掉 `"/news/refresh",`.

删除处理 block (约 line 254-277, `if u.path == "/news/refresh":` 到对应 `return`).

- [ ] **Step 3: 验证语法**

Run: `python3 -c "import ast; ast.parse(open('/Users/augus/.claude/hooks/usage-web.py').read())"`
Expected: 无输出 (解析成功).

- [ ] **Step 4: Mark complete**

---

### Task 4.2: [AUTO] 删除 setupNewsRefresh JS

**Files:**
- Modify: `~/Desktop/ai-project/hooks/usage-web.js:657-694` (删除 setupNewsRefresh IIFE)

- [ ] **Step 1: 读当前代码**

Run: `grep -n "setupNewsRefresh\|news-refresh" ~/Desktop/ai-project/hooks/usage-web.js`
Expected: IIFE 定义 + button id 检查.

- [ ] **Step 2: 删除整个 setupNewsRefresh IIFE** (约 38 行)

从 `// ===== 每日 AI 大事 tab: 刷新按钮 =====` 到 `})();` (包含).

- [ ] **Step 3: 验证**

Run: `grep -c "setupNewsRefresh" ~/Desktop/ai-project/hooks/usage-web.js`
Expected: `0`

- [ ] **Step 4: Mark complete**

---

### Task 4.3: [AUTO] _render_news_panel 删除刷新按钮 + 加 stage badges + 数据更新时间

**Files:**
- Modify: `~/Desktop/ai-project/hooks/usage_web_render.py:1424-1470` (`_render_news_panel`)

- [ ] **Step 1: 读当前代码**

Run: `grep -n "news-refresh-btn\|news_panel\|_render_news_panel" ~/Desktop/ai-project/hooks/usage_web_render.py | head -20`

- [ ] **Step 2: 删除刷新按钮 render 行** (line 1438)

原: `parts.append("<button class='news-refresh-btn' id='news-refresh'>刷新</button>")`
→ 删除

- [ ] **Step 3: 加 stage badges 显示** (在 section-head 里, 紧跟数据时间)

插入:
```python
    # stage_by_source 展示
    stage_map = data.get("stage_by_source", {}) if data else {}
    if stage_map:
        stage_emoji = {"cold": "🥶", "mid": "🌡️", "hot": "🔥"}
        labels = {
            "hackernews": "HN",
            "github_trending": "GitHub",
            "qbitai": "量子位",
            "ithome_tw": "iThome",
        }
        bits = []
        for sid, stage in stage_map.items():
            emoji = stage_emoji.get(stage, "")
            label = labels.get(sid, sid)
            bits.append(f"{label} {emoji}")
        if bits:
            parts.append(f"<span class='news-stage-badges'>阶段: {' · '.join(bits)}</span>")
```

放在 `parts.append(f"<span class='news-vote-count'>✓ {len(voted_urls)} 条已标记</span>")` 之后.

- [ ] **Step 4: 验证**

Run: `python3 -c "import ast; ast.parse(open('/Users/augus/.claude/hooks/usage_web_render.py').read())"`
Expected: 无输出.

- [ ] **Step 5: Mark complete**

---

### Task 4.4: [AUTO] _render_news_item 加 ai_score tooltip

**Files:**
- Modify: `~/Desktop/ai-project/hooks/usage_web_render.py:1313-1380` (`_render_news_item`)

- [ ] **Step 1: 在 title 行加 ai_score 悬浮**

在 `<a class='news-item-title' ...>` 之后, `</div>` (line 1334) 之前, 加:

```python
    ai_score = it.get("ai_score")
    reason = it.get("reason", "")
    if ai_score is not None:
        parts.append(
            f"<span class='news-item-ai-score' title='{html.escape(reason)}'>"
            f"💡 {ai_score}</span>"
        )
```

- [ ] **Step 2: 验证语法**

Run: `python3 -c "import ast; ast.parse(open('/Users/augus/.claude/hooks/usage_web_render.py').read())"`
Expected: 无输出.

- [ ] **Step 3: Mark complete**

---

### Task 4.5: [AUTO] CSS — 加 news-item-ai-score + news-stage-badges 样式

**Files:**
- Modify: `~/Desktop/ai-project/hooks/usage-web.css` (追加新样式, 找现有 news 区附近插入)

- [ ] **Step 1: 在 news-vote-count 样式附近追加**

```css
.news-item-ai-score{
  display:inline-block;
  font-size:11px;
  color:var(--accent);
  margin-left:var(--space-4);
  cursor:help;
}
.news-stage-badges{
  color:var(--text-muted);
  font-size:12px;
}
```

- [ ] **Step 2: 可选删除 news-refresh-btn CSS** (line 1619-1639)

既然按钮删了, CSS 可以同时删 (但保留也无害, 只是死代码).

- [ ] **Step 3: Mark complete**

---

### Task 4.6: [MANUAL] 浏览器验证

**Files:** 无写入.

- [ ] **Step 1: 重启 usage-web**

```bash
# 找现有进程 kill
pkill -f "python3.*usage-web.py" || true
# 重启
python3 ~/Desktop/ai-project/hooks/usage-web.py &
```

- [ ] **Step 2: 浏览器打开 http://localhost:38080**

点击 tab "每日AI大事".

Expected 观察:
- 刷新按钮消失
- 若 ai-news.json 存在:
  - 每条 title 右侧有 `💡 {score}` 悬浮 tooltip (鼠标悬停显示 reason)
  - 顶部显示 "阶段: HN 🥶 · GitHub ..."

- [ ] **Step 3: 若布局错乱**

- 检查 CSS 加的位置 (Task 4.5) 是否在 news 区
- 检查 render_news_panel 新加的 stage_badges 位置是否和其他 meta 并排

- [ ] **Step 4: Mark complete**

---

## Chunk 5: 集成冒烟 + /loop 启动 + 开放问题实测

**范围**: 端到端验证 + 解决 spec §20 开放问题.

**全部** `[MANUAL]` (需要 Claude Code 交互 / 真机验证).

---

### Task 5.1: [MANUAL] 集成冒烟: sentinel 强制触发完整 pipeline

**目的**: 整套流程跑通. **用 sentinel 文件代替手改 SKILL.md** (reviewer 反馈 Blocker #3: 手改若忘了恢复, /loop 会每小时空转).

**前置要求**: Task 2.6 写 ai-news-fetch/SKILL.md 时, on_wakeup 逻辑必须包含 sentinel 检测 (spec 外新增机制):

```python
# ai-news-fetch/SKILL.md on_wakeup 伪代码补丁:
SENTINEL = "/tmp/ai-news-force-run"
if os.path.exists(SENTINEL):
    os.unlink(SENTINEL)       # 自动失效, 不留后遗症
    run_full_pipeline()
    # 下次按正常 10:00 调度
elif now.hour == 10 and now.minute < 30:
    run_full_pipeline()
else:
    ...
```

Task 2.6 写 SKILL.md 时要加这段. 后续冒烟都靠 `touch /tmp/ai-news-force-run` 触发, 不再手改 SKILL.md.

- [ ] **Step 1: 确认 SKILL.md 含 sentinel 检测逻辑** (Task 2.6 做过)

Run: `grep -n "ai-news-force-run" ~/Desktop/ai-project/.claude/skills/ai-news-fetch/SKILL.md`
Expected: 找到 SENTINEL 变量和 os.unlink 调用的说明.

- [ ] **Step 2: tmux 会话里启动 /loop**

```
/loop

使用 ai-news-fetch skill. 每次唤醒时按 skill 的算法判断: 若 /tmp/ai-news-force-run 存在 → 强制跑;
否则命中 10:00-10:30 窗口跑; 否则 ScheduleWakeup 到下一整点.
```

- [ ] **Step 3: 另开终端 touch sentinel, 触发冒烟**

```bash
touch /tmp/ai-news-force-run
# /loop 下次唤醒 (最多 1h 后) 会检测到, 自动 unlink + 跑
# 或主动打断 /loop 的 ScheduleWakeup 让它立刻唤醒
```

若想立刻触发 (不等 1h), 在 Claude Code 里发送 "wake up" 或类似打断消息, 主 agent 收到后会立刻走 on_wakeup 流程.

- [ ] **Step 4: 观察完整 pipeline 跑完**

Expected (约 10-15 分钟):
- 终端输出抓取 → 派 4 个 scorer → 派 summary 批次 → 派 analysis 批次 → 汇总 → 写 ai-news.json → TG 通知

- [ ] **Step 5: 检查 sentinel 已被 unlink**

Run: `ls /tmp/ai-news-force-run 2>&1`
Expected: `No such file or directory` (pipeline 开头就被 unlink, 自动失效保护).

- [ ] **Step 6: 检查产出**

```bash
python3 -c "import json; d=json.load(open('/Users/augus/.claude/usage-stats/ai-news.json')); print(f'version={d.get(\"version\")} sources={len(d.get(\"sources\", []))} stage_by_source={d.get(\"stage_by_source\")}')"
```
Expected: version=2, 4 sources, stage_by_source 含 4 源.

- [ ] **Step 7: 检查 Dashboard**

浏览器刷新 http://localhost:38080/#news → AI 大事 tab. 每条有 summary / workspace_help / claude_usage / ai_score + reason.

- [ ] **Step 8: 检查 TG 通知**

手机查看 Telegram 是否收到 "ai-news 已刷新 N 则" 消息.

- [ ] **Step 9: 若任何一步失败**

记录问题到 `~/Desktop/ai-news-v2-smoke-notes.md`, 排查对应 subagent 或 Python 模块.

- [ ] **Step 10: Mark complete**

---

### Task 5.2: [MANUAL] 开放问题 §20.1: /loop 启动 prompt 调优

**目的**: 第一次跑完后, 根据实际观察调 /loop 启动 prompt 里的表述.

- [ ] **Step 1: 观察第一次跑的行为是否符合预期**

- 唤醒时是否能正确判时间?
- ScheduleWakeup delta 计算是否正确?
- 命中 10:00 后是否正确调用 skill?

- [ ] **Step 2: 如果主 agent 走歪了 (比如没读 skill, 或判时错误)**

调 SKILL.md 里的指令表述, 让主 agent 更明确地:
- 在 on_wakeup 最开头调用 Python 打印 now
- 输出 delta 值后才 ScheduleWakeup
- 给出 verbose 日志

- [ ] **Step 3: Mark complete**

---

### Task 5.3: [MANUAL] Evolve 冒烟 (用假反馈触发)

**目的**: 验证 evolve 触发条件 + source.md 被正确重写 + 备份生成.

- [ ] **Step 1: 手动灌 50 条 HN 反馈到 feedback.json**

```bash
python3 <<'EOF'
import json
from datetime import datetime, timezone
fb = {"votes": {}}
for i in range(50):
    fb["votes"][f"https://example.com/hn-{i}"] = {
        "source": "hackernews",
        "title": f"test {i}",
        "ts": datetime.now(timezone.utc).isoformat(),
    }
with open("/Users/augus/.claude/usage-stats/ai-news-feedback.json", "w") as f:
    json.dump(fb, f, ensure_ascii=False)
print("seeded 50 votes")
EOF
```

- [ ] **Step 2: 修改 hackernews/source.md frontmatter 让它处于"evolve 条件满足"**

改 `evolve_count: 0`, `last_evolve_at:` 留空 → 距上次 evolve 新增反馈 = 50 (>= 20 触发)

- [ ] **Step 3: 再跑一次 pipeline (同 Task 5.3 步骤 1-2)**

- [ ] **Step 4: 观察 evolve 是否触发**

Expected:
- tmux pane 输出 "派 evolve-source-preferences"
- `~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/hackernews/source.md.v0` 备份存在 (原 source.md 的备份)
- `~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/hackernews/source.md` 被重写 (frontmatter `evolve_count: 1`, updated_by=`evolve_v1`)
- `~/Desktop/ai-project/data/ai-news-evolve-log.jsonl` 有一行新记录
- TG 收到 "[ai-news] hackernews 已 evolve 到 v1" 通知

- [ ] **Step 5: 手动回滚测试**

```bash
cp ~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/hackernews/source.md.v0 \
   ~/Desktop/ai-project/.claude/skills/ai-news-filter/sources/hackernews/source.md
```

验证下次跑时 source.md 回到原始偏好.

- [ ] **Step 6: 清理测试数据**

```bash
# 恢复 feedback.json
echo '{"votes":{}}' > ~/Desktop/ai-project/data/ai-news-feedback.json
# 清掉 evolve 产生的备份和 log (可选)
```

- [ ] **Step 7: Mark complete**

---

### Task 5.4: [MANUAL] 正式启动 /loop 长跑

**目的**: 把冒烟改回生产配置, 启动长跑观察.

- [ ] **Step 1: 确认 /loop 已在 tmux 跑** (Task 5.1 启动后就一直在)

- [ ] **Step 2: 重启 /loop 以应用完整 prompt** (可选)

(sentinel 机制不需要改 SKILL.md, 所以不用"改回去". /loop 可以直接继续.)

```
/loop

使用 ai-news-fetch skill. 每次唤醒时判断是否到 10:00,
命中 10:00-10:30 窗口跑完整 pipeline, 其他时间 ScheduleWakeup
(delaySeconds = min(3600, delta_to_next_10am_seconds)).
```

- [ ] **Step 3: detach tmux, 让它后台跑**

`Ctrl-B D`

- [ ] **Step 4: 第一个自然 10:00 观察**

等到明天 10am, 确认:
- TG 收到 "ai-news 已刷新" 通知
- Dashboard 数据更新
- tmux 会话仍存活 (`tmux attach -t ai-news-smoke` 看输出)

- [ ] **Step 5: Mark complete**

---

### Task 5.5: [MANUAL] 长期监控 (7 天 / 30 天)

- [ ] **Step 1: 7 天后检查**

- 反馈数: `python3 -c "import json; d=json.load(open('/Users/augus/.claude/usage-stats/ai-news-feedback.json')); print(f\"votes: {len(d.get('votes', {}))}\")"`
- scorer 触发次数 (从 pipeline log 估)
- 主观评估: Top 10 命中率 (你觉得是不是想看的)

- [ ] **Step 2: 30 天后检查**

- 是否如期有源进入中启动 (某源反馈 >= 10)?
- 若进入中启动, scorer 评分质量怎么样?
- 是否有源进入热启动 (>= 50)? 若是, evolve 是否触发?

- [ ] **Step 3: 根据观察调 source.md 偏好**

evolve 自动修改偏好只对热启动源跑. 冷/中启动源的 source.md 仍是 cold_start 初稿, 可能需要你手动调 (看实际评分结果)

- [ ] **Step 4: Mark complete**

---

## Appendix: 任务数量 + 预估

按 chunk 列出 AUTO / MANUAL 任务数量 (v3, /loop 自主执行 + 迁移版):

- **Chunk 0** (项目迁移): **已在 /loop 启动前手动完成**, 无 /loop 任务.
- **Chunk 1** (Python 基础 + fetcher.yaml 前置): 13 个 AUTO, 0 个 MANUAL. **Task 1.1-1.13 严格串行**.
- **Chunk 2** (架构根基 smoke + subagent + skill): 7 个 AUTO (2.1-2.6), 3 个 MANUAL (2.0a model 覆盖 smoke / 2.0b 并发上限 / 2.7 subagent 冒烟). **Task 2.0a/2.0b 必须最先跑**, 失败则整个 plan 重新设计.
- **Chunk 3** (每源 source.md + examples.md + 抓取冒烟): 4 个 AUTO (3.1-3.4 写文件), 1 个 MANUAL (3.5 抓取冒烟 — 依赖外网).
- **Chunk 4** (Dashboard 改动): 5 个 AUTO (4.1-4.5 写代码), 1 个 MANUAL (4.6 浏览器验证).
- **Chunk 5** (集成 + 长跑 + 监控): 0 个 AUTO, 5 个 MANUAL (5.1 sentinel 集成冒烟 / 5.2 /loop prompt 调优 / 5.3 evolve 冒烟 / 5.4 正式长跑 / 5.5 7/30 天监控).

**合计 (/loop 实际执行部分, 不含已完成的 Chunk 0)**: 29 个 AUTO + 10 个 MANUAL = **39 个 task**. 人工时长约 3-5h (含 Chunk 5 长跑等待).

**/loop 自主执行要点**:
- 每次唤醒按 plan 开头 "执行约束 (bug-first + 当轮不结束)" 流程走.
- AUTO task /loop 自己跑, 通过测试 + git commit 后 mark [x].
- MANUAL task 写 NEED-HUMAN-INPUT.md + TG 通知, ScheduleWakeup 挂起.
- 失败 retry ≤ 3 次, 超 3 次转 MANUAL 等人工.
- Chunk 1 严格串行 (同文件冲突).

**Medium 反馈保留未修 (/loop 执行时顺带处理即可)**:
- Task 1.2 测试用例"融資"边界验证 (/loop 可以 skip, 测试覆盖够了)
- Task 4.3 stage_emoji 违反"生产文件禁 emoji" (/loop 自己替换为"冷/中/热"文字)
- Task 5.3 手改 frontmatter 改用 Python 脚本 (写 NEED-HUMAN-INPUT.md 时附上脚本)
- Chunk 1 行数超 1000 (施工不受影响)

**关键路径 (依赖链)**:
```
人工准备 + Chunk 0 迁移 (已手动完成) → Chunk 1 (13 task, 串行)
                                    → Chunk 2.0a/0b (架构根基 MANUAL, 必须 PASS)
                                    → Chunk 2.1-2.6 (AUTO)
                                    → Chunk 2.7 (subagent 冒烟 MANUAL)
                                    → Chunk 3 (4 AUTO + 3.5 MANUAL)
                                    → Chunk 4 (5 AUTO + 4.6 MANUAL)
                                    → Chunk 5 (全 MANUAL, 长跑)
```

任何一步 MANUAL 验证 FAIL 会回退到前面 AUTO task 修 bug. Chunk 2.0a FAIL 是**致命**, 要重新设计架构.

---

## Plan complete

Saved to `~/Desktop/2026-04-21-ai-news-v2-plan.md`.

**Ready to execute?**

由于 Claude Code 有 subagents, REQUIRED 路径是 **superpowers:subagent-driven-development**: 每个 task 派独立 subagent 执行, 两阶段审查. 下一步你决定:

- 开始执行 (进入 subagent-driven-development skill)
- 仅 Chunk 1 先执行 (全 AUTO 可先跑起来)
- 等等再说
