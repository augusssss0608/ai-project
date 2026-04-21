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
