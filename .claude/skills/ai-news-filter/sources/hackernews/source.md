---
source_id: hackernews
label: Hacker News
updated_by: evolve_v4
last_evolve_at: "2026-07-18T15:00:00+09:00"
evolve_count: 4
---

# HN 评分偏好

## 核心判断维度
- HN 的价值在讨论热度 >= 单纯 score, 评论数 100+ 的优先, 但更优先看话题是否落在 "可上手的 agent / coding 工程" 维度
- 强烈优先: 开源 agent / coding agent 框架发布 (Show HN OSS 项目, GitHub / crates.io repo 形式), MCP / 工具调用类基建, Claude Code / Codex / CLI 类生态变动, agent 工程实践 (control flow, specs, skills, harness engineering, 维护成本)
- 优先: 主流模型 / 基座模型 release 本身 (Claude / GPT / Gemini / DeepSeek / Qwen / Mistral / Kimi / Grok / xAI 的新 release 或 benchmark 突破), 含厂商官方一手 release 页 (anthropic.com/news, qwen.ai/blog, openai.com/index, x.ai/news, blog.google 的模型发布页); 厂商官方技术 postmortem / 研究 blog (Anthropic engineering, Anthropic research, OpenAI research)
- 中性偏优先: 针对 Claude / Copilot / Cursor 等产品的一手实战体验 (含吐槽, 只要是工程师视角的具体复盘, 域名如 hollandtech.net, jamesshore.com, addyosmani.com, simonwillison.net, bsuh.bearblog.dev, acai.sh), 计费 / 限额 / 产品策略变动直接影响开发者日常的
- 关键校正 (evolve_v2 沿用): **来源对不对路不能只看域名, 要看内容性质** ——
  - 官方厂商域名 (anthropic.com 等) 若是 IPO / S-1 / 融资 / 上市 / 商业评论, 一律扣分, 而非因 "Anthropic 出品" 加分
  - 开源 / Show HN / Launch HN 项目若领域偏离 coding agent (如 CAD / 硬件 / 通用设计工具 / Office 套件 / 加密学 / 游戏 AI), 仍扣分, 不因 "开源" 自动加分; 加分仅限项目本身就是 agent / coding / CLI / 模型工程方向
- 校正 (evolve_v3 沿用): **标题里出现熟悉模型名 ≠ 加分, 要看叙事骨架**
  - "GLM 5.2 and the coming AI margin collapse" 虽然带模型名, 但骨架是商业毛利分析, 扣分
  - Terry Tao / 名人科学家的个人博客写 "modern coding agents", 骨架是数学证明 / 学术叙事而非可复现工程流程, 扣分
  - "Working With AI" (htmx 官方) 泛谈 AI 使用, 若没有 Claude Code / Codex / specific harness 的具体落地, 扣分; 反之 SimonW 的 "Unreasonable Effectiveness of HTML with Claude Code" / trq212 的类似复盘 (twitter 也算), 有明确工程流程, 加分
- 新增校正 (evolve_v4): **主流媒体不是死判负, 看事件本身是否是 Claude/Codex 生态变动**
  - theverge 报 "Microsoft starts canceling Claude Code licenses" 是 Claude 生态政策变动, 影响开发者日常工具链 → 加分 (即使 theverge 通常负例)
  - reuters 报 "Zuckerberg says AI agent development going slower" 是名人发言 / 无工程动作 → 扣分
  - 判定要素: 是不是**一次可归因于 Claude/Codex/工具链**的政策/产品变动, 而不是主流媒体域名本身
- 新增校正 (evolve_v4): **twitter/x 链接分正反**
  - Karpathy "I've joined Anthropic" (人事异动, 直接影响 Anthropic 工程组) → 加分
  - trq212 "Using Claude Code: unreasonable effectiveness of HTML" (工程复盘) → 加分
  - MattZirwas "I was wrong about the Midjourney ultra-sound scanner" (无 coding 相关的随口段子) → 扣分
  - "What xAI" gist 类泄漏 / 无上下文截图 → 扣分
- 扣分 (硬规则): 纯融资 / 投资 / IPO / 并购 (S-1, $60B 收购 Cursor, 股市能否消化某公司), 产业政策 / 法律责任 / 政治评论 / 名人发言 (Zuckerberg / Musk / Eric Schmidt / Pope) / 宗教评论, 硬件供应链 / 存储 / 制造成本 / AI Dev Kit 类分析 (AMD Ryzen AI Halo, Huawei flash), 招聘帖, 泛 AI 伦理 / 反 AI / "AI is plagiarism" 类立场文, "AI 是否被滥用 / 是否杀死某行业 / 大家是否在用 AI / 是否该有排除 AI 的科技新闻" 类文化评论与口水文与元讨论, 主权 / 国别专属模型 (GPT-NL, Apertus 之类) 这种与开发者日常工具链无关的政治性发布, 医学 / 学术 conjecture / 教育研究 (Dartmouth AI tutor, Brown 考试作弊) 等远离 coding agent 的应用新闻, 游戏 AI / 图形学 / 加密学 / 音频 / CAD / Office 套件等非 coding 领域的 AI 应用, 顾问 / 服务性质文章 ("we charge $10k a week to delete AI code" 类, 无可下载的工具或方法论), 缺乏可操作信息的标题党 ("Tell HN:" 截断, axios / 主流媒体快讯 / 泄漏 gist)
- "Show HN / Launch HN" 类型: 若是完整开源项目 + 领域是 agent/coding/CLI/模型 + 有 benchmark / 实战表现加分; 若领域跑偏 (CAD/硬件/Office 套件/泛工具/游戏/加密) 或仅 wip demo / 蒸馏小模型炫技 (Needle 之类) 减分

## 用户正例特征 (evolve 自动提取)
- 高频关键词: agent / agents, Claude Code, Codex, coding agent, DeepSeek, Qwen, Gemini, Kimi, Mistral, GPT-5.5, GPT-Live, Grok 4.5, MCP, skills, specs, control flow, OSS, Show HN (open source), postmortem, benchmark (TerminalBench / coding challenge), foundation model, harness, Rust (Zerostack), autoencoders
- 本轮 (v4) 新增 / 强化正例信号:
  - **Claude 生态的第三方产品政策事件即使经主流媒体报出仍是正例**: theverge 报 "Microsoft starts canceling Claude Code licenses" —— 事件性质是工具链政策变动
  - **人事异动 (加入 Anthropic / OpenAI / xAI 核心组) 的 twitter 短公告**: Karpathy "I've joined Anthropic" —— 短促但对生态影响明确
  - **Anthropic research 一手研究页**: "Natural Language Autoencoders: Turning Claude" —— 与 v3 postmortem/engineering 并列的官方一手研究入口
  - **jamesshore.com / hollandtech.net / acai.sh 类 dev blog 深度反思**: "AI coding agent needs to reduce maintenance costs", "Claude is not your architect" —— 都是工程视角的复盘, 有可复现的判断标准
- 沿用正例信号 (v3):
  - 非 Anthropic 阵营的一手基座 / 旗舰模型发布也是强正例, 只要是官方 release 页而非新闻转述: Grok 4.5 (x.ai/news), GPT-Live (openai.com/index), Qwen-Robot Suite (qwen.ai/blog), Claude Opus 4.8 (anthropic.com/news), Gemini 3.5 Flash (blog.google) —— 重点是 "新模型 / 新能力" 的官方一手
  - "Robot / Physical / Agent Frontier" 这类新领域基座 (Qwen-Robot Suite, Qwen3.7-Max) 是正例, 因为是模型能力扩张而非硬件评测
- 偏好模式:
  - 开源 agent / CLI 工程产品 (CrabTrap, SnapState, DeepClaude, Zerostack, dirac, ds4, Semble) — github.com / crates.io / 个人 dev 域名为正例典型来源 (前提: 领域是 agent/coding)
  - 新模型 release 且强调 coding / agent / 基座能力 (Qwen3.6-27B, DeepSeek v4, Kimi K2.6, Mistral Medium 3.5, Gemini 3.5 Flash, Qwen3.7-Max, GPT-5.5, Claude Opus 4.8, Qwen-Robot Suite, Grok 4.5, GPT-Live)
  - Claude / Anthropic 生态的 *工程 / 产品* 深度变动: 官方 postmortem, 限额调整, 第三方 CLI 政策, 用户取消订阅复盘, 微软取消 license, Karpathy 加盟 (注意: 限工程/产品向, 不含融资上市)
  - 工程类博客: agent control flow, specsmaxxing, vibe coding, "Claude is not your architect", HTML effectiveness (with Claude Code), 维护成本 — 一手开发者实战的 blog 域名 (addyosmani.com, simonwillison.net, jamesshore.com, hollandtech.net, bsuh.bearblog.dev, acai.sh)
  - 学术论文 (arxiv) 但限定在 LLM agents 工程脆弱性 / 评测方向 (如 "Constraint Decay: The Fragility of LLM Agents in Back End Code Generation")

## 用户负例特征 (evolve 自动提取)
- 本轮 (v4) 新增 / 强化的负例模式:
  - **名人博客继续踩雷**: Terry Tao "Old and new apps via modern coding agents" 数学向叙事, 无可复现工程流程, 扣分
  - **非 coding 领域 AI 应用继续扫地出门**: OfficeCLI (Office 套件, 即使 github + 开源), Elden Ring 低技 AI (游戏), AI Meets Cryptography (加密学 bug 挖掘), AMD Ryzen AI Halo (硬件 dev kit), Adam CAD Launch HN (CAD)
  - **顾问 / 商业服务性质文章**: "We charge $10k a week to delete AI-generated code" (odra.dev) —— 无工具, 只营销
  - **披模型皮的商业分析**: "GLM 5.2 and the coming AI margin collapse" (martinalderson.com)
  - **主权 / 国别专属模型**: Apertus (瑞士), GPT-NL (荷兰 TNO) —— 政治性发布, 与开发者日常工具链无关
  - **主流媒体报名人无动作发言**: reuters "Zuckerberg says AI agent development going slower" —— 与 v4 校正区分, 这不是 Claude/Codex 生态政策变动
  - **openrouter 类段子式 blog**: "A robot is sprinting towards you. Do you want it running on Claude or Grok?" —— 装成 agent 讨论的营销段子
  - **教育 / 学术作弊 / AI tutor 效果研究**: "Professor denounces mass AI fraud on an exam at Brown" (english.elpais), "AI tutor achieves 0.71-1.30 SD effect size in Dartmouth" (pdf)
  - **文化评论 / 元讨论**: "We need tech news sources which exclude AI" (HN 自帖), "Has AI already killed self-help nonfiction books?" (tim.blog)
  - **twitter 随口段子 / gist 泄漏**: "I was wrong about the Midjourney ultra-sound scanner", "What xAI" gist —— 无 coding 上下文
  - **资本 / 并购**: "SpaceX to buy Cursor for $60B" (reuters) —— 即便主角是熟悉 AI 公司
- 历史负例 (仍适用):
  - 资本 / 上市 / 并购: Anthropic 向 SEC 提交 S-1, "股市能否消化 Anthropic/SpaceX/OpenAI", SpaceX $60B 收购 Cursor, Google $40B 投 Anthropic, Amazon $5B —— 即使主角是熟悉 AI 公司, 金融叙事一律负例
  - 法律 / 责任 / 监管: 德国判 Google 对 AI Overviews 错误答案负责, Adafruit 收到 Flux.ai 律师函, 警察用 AI 伪造证据被调查
  - 文化评论 / 口水文: "认为 AI 能替代员工的 CEO 是烂 CEO", "AI 是否已杀死自助类非虚构书"
  - 教学 / 配置文件而非工具: Stanford CS336 的 CLAUDE.md AI Agent 指南 (是课程配置, 非可上手项目)
  - 招聘帖 (YC hiring), 反 AI / 立场宣言 (Zig anti-AI, "AI is plagiarism", "Less human AI"), 名人 / 宗教 (Pope, Eric Schmidt 被嘘, Musk 败诉)
  - 主流媒体 (axios, techcrunch, bloomberg, theguardian, nbcnews, theverge 非 Claude 相关, economist, reuters 非 Claude 相关, sky news, the-decoder, techdirt, religionnews, adweek, english.elpais) 报道的产业 / 政治 / 八卦
  - 政府 / 国安 / 政策 (NSA, Pope encyclical) 类应用新闻
  - 医学 / 数学 / 物理等领域被 AI "突破" 的新闻 (Harvard triage, discrete geometry conjecture) — 远离 coding 实战
  - 硬件成本 / 数据中心 / 存储分析 (epoch.ai chip cost, Norway Huawei flash, eighth-gen TPU, AMD Ryzen AI Halo)
  - 商业模式质疑 / 盈利分析 ("Is AI Profitable Yet", ChatGPT ad placements, GLM 5.2 margin collapse)
  - 标题不完整 / 内容预览缺失的 HN 自帖 ("Tell HN: I", ycombinator item id 自帖)
  - 泛哲学 / 法则化口号文 ("Three Inverse Laws of AI")
