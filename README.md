# ai-project

AI / 统计系统独立项目, 从 ~/.claude/hooks/ + ~/.claude/usage-stats/ 迁移而来.

详见 docs/plan.md. /loop 执行中的进度看 progress/progress.md.

## 快速启动

### 生产 AI 大事 /loop (每天 10:00 抓新闻)
    tmux new -s ai-news-production
    cd ~/Desktop/ai-project
    claude --model sonnet
    /loop

### 施工 /loop (跑 plan 用)
    tmux new -s ai-project-exec
    cd ~/Desktop/ai-project
    claude --model sonnet
    /loop

### Dashboard (Chunk 0 完成后启动)
    python3 ~/Desktop/ai-project/hooks/usage-web.py
    # 打开 http://localhost:38080

## 目录

- `.claude/{skills,agents}/` — 项目级 skill 和 subagent
- `hooks/` — 所有 Python 代码 (dashboard + ai_news pipeline)
- `data/` — 数据文件 (gitignore)
- `docs/` — spec + plan
- `progress/` — /loop 执行状态 (gitignore)
