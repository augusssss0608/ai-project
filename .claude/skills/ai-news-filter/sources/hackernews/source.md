---
source_id: hackernews
label: Hacker News
updated_by: evolve_v2
last_evolve_at: "2026-06-20T14:30:00+09:00"
evolve_count: 2
---

# HN 评分偏好

## 核心判断维度
- HN 的价值在讨论热度 >= 单纯 score, 评论数 100+ 的优先, 但更优先看话题是否落在 "可上手的 agent / coding 工程" 维度
- 强烈优先: 开源 agent / coding agent 框架发布 (Show HN OSS 项目, GitHub repo 形式), MCP / 工具调用类基建, Claude Code / Codex / CLI 类生态变动, agent 工程实践 (control flow, specs, skills, 维护成本)
- 优先: 主流模型 / 基座模型 release 本身 (Claude / GPT / Gemini / DeepSeek / Qwen / Mistral / Kimi 的新 release 或 benchmark 突破), 含厂商官方一手 release 页 (anthropic.com / qwen.ai 的模型发布); 厂商官方技术 postmortem / 研究 blog (Anthropic engineering, OpenAI research)
- 中性偏优先: 针对 Claude / Copilot / Cursor 等产品的一手实战体验 (含吐槽, 只要是工程师视角的具体复盘), 计费 / 限额 / 产品策略变动直接影响开发者日常的
- 关键校正 (本轮反馈): **来源对不对路不能只看域名, 要看内容性质** ——
  - 官方厂商域名 (anthropic.com 等) 若是 IPO / S-1 / 融资 / 上市 / 商业评论, 一律扣分, 而非因 "Anthropic 出品" 加分
  - 开源 / Show HN / Launch HN 项目若领域偏离 coding agent (如 CAD / 硬件 / 通用设计工具), 仍扣分, 不因 "开源" 自动加分; 加分仅限项目本身就是 agent / coding / CLI / 模型工程方向
- 扣分 (硬规则未截下来的): 纯融资 / 投资 / IPO / 并购 (S-1, $60B 收购, 股市能否消化某公司 之类), 产业政策 / 法律责任 / 政治评论 / 名人发言 / 宗教评论, 硬件供应链 / 存储 / 制造成本类分析, 招聘帖, 泛 AI 伦理 / 反 AI / "AI is plagiarism" 类立场文, "AI 是否被滥用 / 是否杀死某行业 / 大家是否在用 AI" 类文化评论与口水文, 主权 / 国别专属模型 (GPT-NL 之类) 这种与开发者日常工具链无关的政治性发布, 医学 / 学术 conjecture 等远离 coding agent 的应用新闻, 缺乏可操作信息的标题党 ("Tell HN:" 截断, axios / 主流媒体快讯)
- "Show HN / Launch HN" 类型: 若是完整开源项目 + 领域是 agent/coding/CLI/模型 + 有 benchmark / 实战表现加分; 若领域跑偏 (CAD/硬件/泛工具) 或仅 wip demo / 蒸馏小模型炫技 (Needle 之类) 减分

## 用户正例特征 (evolve 自动提取)
- 高频关键词: agent / agents, Claude Code, coding agent, DeepSeek, Qwen, Gemini, Kimi, Mistral, GPT-5.5, MCP, skills, specs, control flow, OSS, Show HN (open source), postmortem, benchmark (TerminalBench / coding challenge), foundation model
- 本轮新增正例信号:
  - 一手基座 / 旗舰模型发布本身就是强正例, 即便是厂商官方 release 页: Claude Opus 4.8 (anthropic.com/news), Qwen-Robot Suite 基座模型套件 (qwen.ai/blog) —— 重点是 "新模型 / 新基座能力" 而非营销叙事
- 偏好模式:
  - 开源 agent / CLI 工程产品 (CrabTrap, SnapState, DeepClaude, Zerostack, dirac, ds4) — github.com / crates.io / 个人 dev 域名为正例典型来源 (前提: 领域是 agent/coding)
  - 新模型 release 且强调 coding / agent / 基座能力 (Qwen3.6-27B, DeepSeek v4, Kimi K2.6, Mistral Medium 3.5, Gemini 3.5 Flash, Qwen3.7-Max, GPT-5.5, Claude Opus 4.8, Qwen-Robot Suite)
  - Claude / Anthropic 生态的 *工程 / 产品* 深度变动: 官方 postmortem, 限额调整, 第三方 CLI 政策, 用户取消订阅复盘, 微软取消 license, Karpathy 加盟 (注意: 限工程/产品向, 不含融资上市)
  - 工程类博客: agent control flow, specsmaxxing, vibe coding, "Claude is not your architect", HTML effectiveness, 维护成本 — 一手开发者实战的 blog 域名 (addyosmani.com, simonwillison.net, jamesshore.com, hollandtech.net, bsuh.bearblog.dev, acai.sh)
  - 学术论文 (arxiv) 但限定在 LLM agents 工程脆弱性 / 评测方向

## 用户负例特征 (evolve 自动提取)
- 本轮强化的负例模式:
  - 资本 / 上市 / 并购: Anthropic 向 SEC 提交 S-1 草案, "股市能否消化 Anthropic/SpaceX/OpenAI", SpaceX 60B 收购 Cursor —— 即使主角是熟悉的 AI 公司, 只要是金融叙事一律负例
  - 法律 / 责任 / 监管: 德国判 Google 对 AI Overviews 错误答案负责, Adafruit 收到 Flux.ai 律师函, 警察用 AI 伪造证据被调查
  - 文化评论 / 口水文: "认为 AI 能替代员工的 CEO 是烂 CEO", "并非所有人都在用 AI", "AI 是否已杀死自助类非虚构书", openrouter "机器人朝你冲来你想要 Claude 还是 Grok" 这类营销/段子贴
  - 主权 / 国别专属模型: GPT-NL 荷兰主权语言模型 —— 与开发者工具链无关的政治性发布
  - 教学 / 配置文件而非工具: Stanford CS336 的 CLAUDE.md AI Agent 指南 (是课程配置, 非可上手项目)
  - 跑偏领域的开源项目: Launch HN Adam (YC) 开源 AI CAD —— 开源但领域是 CAD, 不是 coding agent
- 历史负例 (仍适用):
  - 融资金额 ($5B / $40B), TPU / 芯片硬件, 招聘帖 (YC hiring), 反 AI / 立场宣言 (Zig anti-AI, "AI is plagiarism", "Less human AI"), 名人 / 宗教 (Pope, Eric Schmidt 被嘘, Musk 败诉)
  - 主流媒体 (axios, techcrunch, bloomberg, theguardian, nbcnews, theverge 非 Claude 相关, economist, reuters, sky news, the-decoder, techdirt, religionnews, adweek) 报道的产业 / 政治 / 八卦
  - 政府 / 国安 / 政策 (NSA, Pope encyclical) 类应用新闻
  - 医学 / 数学 / 物理等领域被 AI "突破" 的新闻 (Harvard triage, discrete geometry conjecture) — 远离 coding 实战
  - 硬件成本 / 数据中心 / 存储分析 (epoch.ai chip cost, Norway Huawei flash, eighth-gen TPU)
  - 商业模式质疑 / 盈利分析 ("Is AI Profitable Yet", ChatGPT ad placements)
  - 标题不完整 / 内容预览缺失的 HN 自帖 ("Tell HN: I")
  - 泛哲学 / 法则化口号文 ("Three Inverse Laws of AI")
