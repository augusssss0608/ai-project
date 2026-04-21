resolved: false

## Task 2.0a: 架构根基 smoke — subagent model 覆盖验证

/loop 已自动完成: 创建 `.claude/agents/news-scorer.md` (model: claude-haiku-4-5)

**这是整个项目的关键前提**: 若 subagent model 覆盖不生效, spec §4 + §9 架构作废, 项目中止.

---

### 你要做的 (Steps 2-7):

**Step 2: 在当前 tmux 会话或新窗口启动 Sonnet Claude Code**
```bash
cd ~/Desktop/ai-project
claude --model sonnet
```

**Step 3: 在 Claude Code 里派 news-scorer subagent**
```
用 Agent tool 派 subagent_type: "news-scorer", prompt: "hello"
```
等它返回 (应该打印 "hello from news-scorer" 并写 /tmp/scorer-probe.json)

**Step 4: 检查 Anthropic dashboard 账单**
- 打开 https://console.anthropic.com/ → Usage
- 找最近 5 分钟的调用
- 看 model 字段是 "claude-haiku-4-5-20251001" 还是 "claude-sonnet-4-6"

**Step 5/6: 根据结果修改本文件顶部**

若 model 是 **haiku** (覆盖成功):
```
resolved: true
verdict: PASS
```

若 model 是 **sonnet** (覆盖失败):
```
resolved: true
verdict: FAIL
```
— /loop 收到 FAIL 后将中止项目, 写入架构失败原因, 等你决定是改 subprocess 路径还是放弃.

---

### /loop 状态:
- 已 ScheduleWakeup 2h, 下次唤醒会读本文件的 resolved 字段
- 如急处理完, 可直接发消息 "resolved" 打断等待

### 日志:
- progress/logs/ (本任务无 subprocess log)
