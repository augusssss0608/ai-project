# ai-project

Claude Code 使用统计 dashboard + AI 大事每日聚合。原在 `~/.claude/hooks/` + `~/.claude/usage-stats/`，迁到独立项目做 git 版本管理。

## 快速启动

**Dashboard**（端口 38080）：

    python3 ~/Desktop/ai-project/hooks/shared/http/server.py
    # 打开 http://localhost:38080

5 个 tab：总览 / 工具使用 / 上下文 / 记忆 / 每日 AI 大事。

**AI 大事抓取 debug**（只跑 fetchers + filters，不调 AI）：

    python3 ~/Desktop/ai-project/hooks/ai_news/fetch_debug.py
    # 输出 /tmp/ai-news-raw-{source_id}.json

完整 pipeline 由 `/loop` + ai-news-fetch skill 驱动，不走这个脚本。

**ai-news 单元测试**：

    cd ~/Desktop/ai-project/hooks && python3 -m unittest discover ai_news/data/tests

**清空使用统计**（events.db 重新计数）：

    sqlite3 ~/Desktop/ai-project/data/events.db "DELETE FROM events; VACUUM;"
    date -u +"%Y-%m-%dT%H:%M:%SZ" > ~/Desktop/ai-project/data/last-cleared.txt

清零时间会显示在 dashboard 顶部。

## 目录结构（feature-first）

    hooks/
    ├── shared/                 公共底座
    │   ├── http/server.py      HTTP 入口（请求路由 + archive/restore endpoint）
    │   ├── http/render.py      页面骨架 + 共享渲染（header / tab bar / health strip）
    │   ├── data/queries.py     SQLite 查询 + 聚合
    │   ├── infra/core.py       常量 / 路径 / EVENT_TYPES / cold sections
    │   ├── infra/summary.py    AI 中文摘要（claude -p 子进程 + 磁盘缓存）
    │   └── static/             共享 CSS / JS (base.css / base.js)
    ├── overview/               总览 tab（Hero + Today + 健康条）
    ├── usage/                  工具使用 tab（概览表 + sparkline 行 + 状态过滤）
    ├── context/                上下文 tab（路由足迹 + session 时间线）
    ├── memory/                 记忆 tab（auto-memory 浏览 + Compact 时间轴）
    ├── ai_news/                每日 AI 大事 tab
    │   ├── data/               fetchers / filters / feedback / history / evolve + tests
    │   ├── render.py           tab 渲染
    │   ├── fetch_debug.py      debug 抓取入口（绕过 pipeline）
    │   └── static/             ai_news 专属 CSS / JS
    ├── tracker/                PostToolUse hook + 数据维护脚本
    │   ├── tracker.sh          事件采集（Read/Agent/Skill → events.db）
    │   ├── archive-cold.sh     冷藏 skill/subagent 自动归档（可逆）
    │   └── report.sh           命令行报表
    ├── workspace-lint/         workspace 配置检查（trigger.sh + lint_runner.py）
    └── tg_notify.py            Telegram Bot API 直发脚本（ai-news pipeline 用）

其他顶级目录：

- `.claude/{skills,agents}/` — ai-news pipeline 用的 skill / subagent 定义（项目级）
- `cloud-sync/` — AI 大事数据（ai-news.json / ai-news-feedback.json / ai-news-history.jsonl），需要跨机同步
- `data/` — 本机运行时数据 [gitignore]
  - `events.db` — 使用统计事件 SQLite（单一真理源）
  - `last-cleared.txt` — 上次清零时间（dashboard 顶部展示）
  - `summaries.json`、`summary-quota.json` — AI 摘要缓存 + 日额度
  - `archive-log.jsonl` — skill/subagent 归档记录
  - `tracker-errors.log` — tracker.sh 错误日志
  - `lint-status.json` — workspace-lint 最近一次结果
  - `.threads-session.json` — Threads 抓取凭据（参考 `.example`）
- `docs/` — 历史设计文档（`spec.md` AI 大事 v2 设计 / `threads-sniff.md` Threads 凭据抓取手册）
