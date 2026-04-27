# ai-project 工作区说明

本项目托管 Claude Code 使用统计 dashboard + 每日 AI 大事 pipeline + memory/overview/usage 等可视化面板.

## Git 提交硬规则

**任何代码改动都要提交**, 不要积压到 working tree:

- `.py` / `.md` / `.yaml` / `.css` / `.js` / `.json` (除 data/ progress/ 外)
- `.claude/skills/**` / `.claude/agents/**`
- `hooks/**` / `docs/**`

**唯一例外: `/loop` 主 agent 自动跑的 ai-news pipeline 产出不提交** —— 这些是运行时数据, 不是代码:

- `data/ai-news.json` (.gitignore 已忽略)
- `data/ai-news-feedback.json` (.gitignore 已忽略)
- `data/ai-news-history.jsonl` (.gitignore 已忽略)
- `progress/progress.json` 的心跳更新 (虽然该文件被 git 追踪, 但 /loop 触发的 last_heartbeat / current_task 推进不算代码改动)
- 其他 `/tmp/ai-news-*.json` 中间产物 (本来就在 /tmp)

判定口诀: **是不是用户或 Claude 主动改的代码** → 是就提交; **是不是 /loop 跑出来的状态/数据** → 是就跳过.

如果跳过这条规则, 会导致: 改动越积越多 → 后续要分组重排 commit 浪费时间; 历史不可追溯, 出 bug 想 bisect 都没切口; 多 session 工作时容易把别人的改动当自己的提交.

## 提交风格

参考已有 commit (见 `git log --oneline`):

- 前缀英文 conventional commit (`feat(ai-news):` / `refactor(overview):` / `style(hooks):` / `chore(progress):` / `fix(...)`), 冒号后描述用中文
- 跨模块改动按模块拆 commit, 不要塞一个大 commit
- co-author 行保留

## 项目结构速览

```
.claude/
  agents/      # subagent prompt (news-scorer / news-summary / news-analysis / evolve-source-preferences)
  skills/      # ai-news-fetch (主编排) + ai-news-filter (源配置 sources/{hackernews,github_trending,simonw,threads,...})
hooks/
  ai_news/     # AI 大事抓取 + 渲染 (data/ + render.py + static/)
  overview/    # 总览 tab
  usage/       # 使用统计 tab
  memory/      # memory 文件浏览 tab
  context/     # context 信息 tab
  shared/      # 跨 tab 公共代码 (data/queries.py, infra/core.py, http/render.py, static/base.css/js)
  tracker/     # 数据采集 (tracker.sh / report.sh)
  tg_notify.py # 独立 TG 推送脚本
data/          # gitignored, 运行时数据
progress/      # gitignored 顶层目录, 但 progress.json 被追踪 (项目自身任务跟踪状态)
```

## /loop 与 ai-news pipeline

每日 10:00 JST `/loop` 主 agent 跑 ai-news-fetch skill, 见 `.claude/skills/ai-news-fetch/SKILL.md`.

- 强制触发: `touch /tmp/ai-news-force-run`, 下次 /loop 唤醒会跑
- 数据落点: `data/ai-news.json` (展示) + `data/ai-news-history.jsonl` (历史) + `data/ai-news-feedback.json` (用户反馈)
- 阶段判定: `from ai_news.data.feedback import load_feedback, get_stage` (注意路径是 `ai_news.data.feedback`, 不是 `ai_news.feedback`)
