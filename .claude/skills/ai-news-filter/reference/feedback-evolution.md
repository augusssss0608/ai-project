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
