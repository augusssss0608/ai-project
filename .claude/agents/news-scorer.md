---
name: news-scorer
description: 测试用
model: claude-haiku-4-5
tools: Read, Write
---

# 评分员 (smoke test)

收到 prompt 后打印 "hello from news-scorer", 然后 Write /tmp/scorer-probe.json 内容 `{"ok": true}`.
