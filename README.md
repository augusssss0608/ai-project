# ai-project

Claude Code 使用统计 + AI 大事每日聚合. 原在 `~/.claude/hooks/` + `~/.claude/usage-stats/`, 迁到独立项目做 git 版本管理.

## 快速启动

**Dashboard** (端口 38080):

    python3 ~/Desktop/ai-project/hooks/shared/http/server.py
    # 打开 http://localhost:38080

**AI 大事抓取 (debug, 只抓不走 AI)**:

    python3 ~/Desktop/ai-project/hooks/ai_news/fetch_debug.py

**运行测试**:

    cd ~/Desktop/ai-project/hooks && python3 -m unittest discover ai_news/data/tests

## 目录结构 (feature-first)

    hooks/
    ├── shared/              公共底座
    │   ├── http/            HTTP 服务器 + 页面骨架 (render.py)
    │   ├── data/            共享 SQL (queries.py)
    │   ├── infra/           配置 + AI 摘要引擎 (core.py, summary.py)
    │   └── static/          CSS / JS
    ├── overview/            总览 tab (Hero + Today + Health)
    ├── usage/               工具使用 tab (Active + Cold)
    ├── context/             上下文 tab (CLAUDE.md 分析)
    ├── memory/              记忆 tab (Memory + Compact)
    ├── ai_news/             每日 AI 大事 tab
    │   ├── data/            抓取/过滤/反馈/历史/evolve + tests
    │   ├── render.py        tab 渲染入口
    │   └── fetch_debug.py   debug 抓取入口
    └── tracker/             Claude Code PostToolUse hook + 数据维护脚本

其他顶级目录:

- `.claude/{skills,agents}/` — 项目级 skill 和 subagent
- `data/` — 运行时数据 (events.db / ai-news.json / feedback.json) [gitignore]
- `docs/` — spec + plan (历史设计文档)
- `progress/` — 实施期进度记录 [gitignore]
