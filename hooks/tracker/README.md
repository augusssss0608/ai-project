# tracker/

Claude Code 使用统计的**事件采集层**：通过 hook 监听工具调用，把事件写入 SQLite。dashboard 读这个数据库出图。

## 数据流

```
Claude Code (你正常用)
        │
        ├── PostToolUse hook ────┐
        └── UserPromptSubmit hook ┤
                                  ▼
                              tracker.sh
                                  │
                                  └─→ events.db (SQLite 单一真理源)
                                          │
                                          └─→ dashboard / report.sh 读取
```

Hook 配置在 `~/.claude/settings.json` 的 `hooks.PostToolUse` 和 `hooks.UserPromptSubmit`。`~/.claude/hooks/usage-tracker.sh` 是 symlink → 本目录的 `tracker.sh`。

## tracker.sh 抓什么

每次 hook 触发时，tracker.sh 按 `tool_name` / `hook_event_name` 分类写入：

| event_type | 触发条件 | 字段 |
|---|---|---|
| `skill_read` | Read `*/skills/*/SKILL.md` | name=skill 名, scope=user/project/plugin |
| `clinerule_read` | Read `*/.claude/docs/*` | name=相对路径 |
| `claude_md_read` | Read `*/CLAUDE.md` | name=global/root/subproject |
| `agents_md_read` | Read `*/AGENTS.md` | 同 CLAUDE.md |
| `memory_read` | Read `*/memory/*.md` | name=文件名 |
| `subagent` | Agent / Task tool | name=subagent_type, description=任务摘要 |
| `skill_explicit` | Skill tool | name=skill 名（含 `plugin:cmd` 形态） |
| `user_prompt` | UserPromptSubmit hook | name=prompt 前 200 字 |

每条 event 都附 `ts` (UTC ISO)、`session` (Claude Code session_id)。

## 目录内文件

| 文件 | 角色 |
|---|---|
| `tracker.sh` | hook 入口（PostToolUse + UserPromptSubmit），唯一写 events.db 的脚本 |
| `report.sh` | CLI 排行报表（不依赖 dashboard） |

## 数据文件

位置：`~/Desktop/ai-project/data/`

| 文件 | 说明 |
|---|---|
| `events.db` | SQLite 单一真理源（dashboard 和 report.sh 都读这个） |
| `tracker-errors.log` | hook 内部失败时写入（sqlite 写失败 / schema init 失败） |
| `archive-log.jsonl` | 历史遗留：旧 `.disabled/` 停用机制的审计日志，现已改为手动停用，不再写入 |
| `last-cleared.txt` | 上次手动清零 events.db 的时间，dashboard 顶部显示 |

## 常用命令

**清空事件重新统计**：

    sqlite3 ~/Desktop/ai-project/data/events.db "DELETE FROM events; VACUUM;"
    date -u +"%Y-%m-%dT%H:%M:%SZ" > ~/Desktop/ai-project/data/last-cleared.txt

**CLI 看排行**：

    bash ~/Desktop/ai-project/hooks/tracker/report.sh         # 30 天 all
    bash ~/Desktop/ai-project/hooks/tracker/report.sh 7       # 7 天
    bash ~/Desktop/ai-project/hooks/tracker/report.sh 30 skill   # 只看 skill

类别：`skill / clinerule / subagent / explicit / claude / agents / memory / all`

**手动停用工具**（dashboard 只展示状态，不提供停用按钮）：

- 停用 agent：把 `<name>.md` 改名成 `<name>.md.disabled`（Claude Code 的 `*.md` 发现机制会跳过它；去掉后缀即恢复）。
- 停用 skill：`/skills` 菜单选中按空格切到 `off`（写入 `settings.local.json` 的 `skillOverrides`；再切回 `on` 恢复）。

dashboard 读上述两个来源标记「已停用」，与 Claude Code 实际能否调用一致。

## 故障诊断

**完全没事件进来**：

    ls -la ~/Desktop/ai-project/data/events.db   # 文件存在吗
    grep PostToolUse ~/.claude/settings.json     # hook 配置在吗
    bash -n ~/Desktop/ai-project/hooks/tracker/tracker.sh  # 语法
    tail -20 ~/Desktop/ai-project/data/tracker-errors.log  # 有错误吗

**手动跑一次 tracker 测试**（验证写入链路）：

    echo '{"tool_name":"Read","tool_input":{"file_path":"/tmp/test/.claude/skills/foo/SKILL.md"},"session_id":"manual-test"}' \
      | bash ~/Desktop/ai-project/hooks/tracker/tracker.sh
    sqlite3 ~/Desktop/ai-project/data/events.db \
      "SELECT * FROM events WHERE session='manual-test';"

**dashboard 看不到数据但 db 有事件**：先确认 dashboard server 已重启（events 是窗口查询，server 缓存通常不是问题；但重启总没坏处）。

## 设计原则

- **SQLite 单一真理源**：events.db 损坏概率极低，所有写入和读取都走这一份
- **hook 失败不能阻塞工具调用**：tracker.sh 用 `2>/dev/null` 静默处理；失败写 `tracker-errors.log` 不向 stderr 抛
- **archive 可逆**：所有 `.disabled/` 操作都记录到 `archive-log.jsonl`，错了能恢复
- **schema 自愈**：每次启动 `CREATE TABLE IF NOT EXISTS`，文件存在但表丢了也能补建
