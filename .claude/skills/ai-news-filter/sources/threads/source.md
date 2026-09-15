---
source_id: threads
label: Threads (For You)
updated_by: evolve_v10
last_evolve_at: "2026-09-15T14:30:00+09:00"
evolve_count: 10
---

# Threads For You 偏好

## 核心判断维度
- 优先: AI 研究员 / 从业者的一手观察、模型发布与使用心得、工具 / SDK 新功能、争议性观点、跨界专家 (学者 / 数学家) 谈 AI
- 重点关注 Claude / Codex / Anthropic / OpenAI / Google DeepMind / DeepSeek 生态的深度更新 (新指令 / 新功能 / 算力布局 / Agent 模板 / 官方插件 / 版本 release notes / 用量上限 / 计费模型变化 / 官方手册 / 记忆系统架构翻新 / Dynamic Workflows 类工作流范式 / 手机后台跑 Agent / Slack 内嵌 Claude Tag / 内建 skill 新增 / 大厂跨界合作 / 合规机制如输出浮水印)
- Claude Code / Codex / Cursor / Antigravity 类 AI coding 工具的工程化议题尤其加分: Agent View、Agent harness、Harness Engineering 方法论、subagent 成本与选型、Skills guide、Agent SDK 计费、week limit 调整、`/goal` 自主开发与长任务、auto mode / `/usage` 用量拆解 / `/code-review` / `/design` / `/checkup` 类新内建指令、权限控制 + skills + 多层 `.claude` 专案设定、Goal / 终点条件类自动化机制、Chrome 扩充背景多分页、施工日誌 prompt (边写边记决策点)、Claude Agent SDK ↔ Codex 跨平台跳槽心得、Codex 自我提升 prompt (回看 30 天 session 找重复手动操作)、Skill 自我改进循环、Loop 编排的 token 消耗优化实测
- **单个指令 / 单个机制的「微更新 + 官方理由解读」是稳定正例** (例: `/code-review` 从 inline 改成 background subagent 并解释「review 不再塞满 conversation、不卡 stacked slash」、`/design` 把设计与程式的距离缩成一个指令、`/checkup` 帮 AI 编程环境做健检) — 关键是说清「变了什么 + 官方为什么这样改 + 对工作流的影响」, 不必是大版本发布
- **子代理 / 模型选型 / 配置层级的细粒度实操 tip 加分** (例: 把 Fable 子代理预设模型固定成 Opus 而非自动选择) — 这类「多数人忽略的一个设定细节」信息密度高, 优先
- **Claude Code / Codex 逐版 release notes 拆解是最稳定的高频正例 (brew.agent 源)**: Claude Code 2.1.x 每一版 (132 / 140 / 146 / 186 / 187 / 193 / 196 / 198 / 199 / 218 / 221) + Codex CLI 0.14x (预算管理 / 多代理委派 / 插件体验优化) 每次都收. 只要标题说清"这版 N 项 CLI 变更"型逐版拆解, 即使版本号密集也要保留 — 这是用户明确高频点赞的稳定源. 无需担心霸屏, brew.agent 逐版列表本身就是核心信号
- AI coding 成本 / 部署判断信号 (例: 微软给员工试用 Claude Code 六个月后砍掉的成本訊號、Copilot 改量计费实测、Anthropic 计费大地震、Agent SDK & `claude -p` 改 credit 计价、"顶尖 AI 正在变成奢侈品"的定价反思、"Anthropic 6/15 大地震: 订阅制算力限制在人类盯着萤幕互动的场景, 无人值守工作流被严苛紧箍咒"、**新模型「价格对半砍但能力碾压」型定价拆解、「把 Agent 使用成本压下来」型成本结构解读**) 优先 — 这类"商业行为背后揭示的真实成本结构 + 规则变化对无人值守 / Agent 工作流的具体冲击"比单纯排行榜更值得收
- **算力 / 合约类要按「有没有落到用户能力上」分流**: 讲清算力如何直接回馈到订阅者额度与模型能力的 (例: Anthropic 拿下 SpaceX Colossus 1 全部运算容量, 一个月内上线 300+ MW / 22 万颗 GPU, 直接回馈 Pro 与 Max 订阅者) 收; **纯商业合约 / 算力供应长约 / 财报数字公告 (例: TeraWulf 拿下 Anthropic 20 年 190 亿美元长约、Google 400 亿押注 Anthropic、"OpenAI 联发科 Qualcomm 供应链") 只是新闻搬运型报导, 无作者分析、无成本结构解读、无对用户的具体影响, 降权**
- 大厂 x AI 公司跨界合作型速报 (例: SpaceX 与 Claude 宣布合作) 加分 — 这类落地案例反映 AI 生态渗透边界, 尤其带具体应用场景猜测或深度分析更好. 与"纯合约金额公告"不同: 合作型速报揭示应用场景走向
- CLAUDE.md / 设定档 / repo 内项目知识管理类爆款加分 — 反映"AI 时代项目背景知识如何沉淀"的元话题; 尤其带反直觉结论 (例: "设定档越长越强? 刚好相反"、**"Claude 5 删掉 80% 规则, 效果没有变差"**、karpathy CLAUDE.md 冲上 GitHub Trending #1 220K stars 多数人还没读) 更加分. Anthropic / OpenAI 官方内部知识管理方式曝光型 (例: sliven0722 揭 Anthropic 内部知识管理) 也加分
- **社群传言 / 反向验证型争议帖加分** (例: "现在有个传言: Superpowers 会让原本很强的 AI 模型变弱") — 对热门 skill / 框架提出质疑并尝试验证的内容, 比一边倒安利更有价值
- **Claude Code skill / 插件生态的榜单与竄起观察加分** (例: 本週竄起的 Claude Code skill Top 3) — 带「这週哪些 skill 起来了 + 各自解决什么」的生态盘点; 但只列名字没说用途的清单不收
- GitHub Trending #1 / 前几名异常信号类速报 (headroom、Understand Anything 59.2k stars、karpathy CLAUDE.md 220K stars、DeusData codebase-memory-mcp 一路狂飙 +7,674 星冲到 17.8k) 加分 — 用户持续点赞"今天 GitHub Trending 第 X 名是 Y"型一手榜单观察 (tripleh.ai / govin999999 / martech_bb / ekcheungai); 关键是"带异常冲榜信号 + 项目能做什么". **但把 Hacker News 当日热帖整篇搬到 Threads 的二手速报降权 (我们已有独立 hackernews 源, 属重复覆盖)**
- 实战工作流值得加分: Dynamic Workflows / Claude Code workflows 改变写 code 方式的实测、SDD / MCP / Agent Canvas / Browser-use / Hermes Agent / self-improvement loop / Dreaming / Managed Agents 三件套 / Claude Code 做完整 app 的端到端案例 / Claude Code + MCP 组合工作流 / **用 Claude Code 指挥 Codex CLI 的多种编排方式 (跨工具 orchestration)** / 用 html 审批提案 / Vibe Marketing 实际案例 / Midscene 类 AI 网页自动化开源工具 (说清楚在自动化测试与网页脚本场景里替换了什么) / Loop 编排省 token 实测 / OpenAI Codex 官方 52 个使用案例整理 (含 Skill 外挂对照) (要看到落地链路 + 设计取舍 + 跟现有方案差在哪, 不只是点名工具)
- **示范 / 录制型学习能力的功能速报加分** (例: Claude Cowork「看你操作一次, 就永远会做了」) — 交互范式变化 + 能力边界描述清楚即可
- **Vibe coding 圈新趋势速报加分** (例: marvinpick 观察到的最新趋势型帖) — 这类"XX 圈出现新趋势"若能识别到工程实践层面的转向, 有指向性
- 元思考与行业洞察类好文 (例: "95% 自动化不算自动化"、"Token = 钱"、"单线程 vs 多线程 AI"、"不是比 prompt 写得漂亮"、"如果你还在研究怎么写 Prompt 可能已落后下一阶段"、"Agent Engineering = SE 变形"、"AI coding 进入 usage ceiling 竞争"、"Anthropic 做的已经不是聊天 AI"、"现在 AI 的价值不是完全服从而是能帮你完成任务") 优先, 哪怕作者不知名
- 商业模式 / 算力结构分析 / 产业链 / 计费 / 流量变化 (Copilot 量计费 +10x 实测、Cloudflare 在 AI 时代收"过路费"的护城河分析、Agent SDK 改 Credit、Claude Code 周用量 +50% 官方直接宣布 (Pro / Max / Team / Enterprise 全部自动套用不用 opt-in)、Anthropic 计费规则大地震、5h limit token 体感数据、AI 导流洗牌带数据的流量结构分析) 优先; 但要有"作者自己的结构性分析", 不是单纯合约金额公告
- **额度 / 限制变化要看是否带跨厂对照或结构解读**: 带竞品对照的 (例: "Claude 宣布 Fable 延长, OpenAI Tibo 宣布 Codex 暂时移除 5h 限制并即将重置用量") 收; **单纯"额度突然满血复活 / 无预警重置"的多方转述型速报降权 — 这类同一天会被 5-10 个账号刷屏, 只留信息最全或带对照的一条**
- **模型发布 / 排名 / 暂停复活 / 出口管制封锁的连续追踪是用户高频正例** (例: Claude Opus 4.7 / 4.8 团队讨论、Claude Sonnet 5 发布、Claude Opus 5 价格对半砍、Claude Fable 5 / Mythos 5 在 Arena.ai 三榜夺第一 → 因美国出口管制被 Anthropic 无预警封锁 → 白宫拟松绑 → 高层松口"数日内"重新开放 → 重新上线但一般用户可能失望) — 同一模型 saga 的关键节点都收, 但要带排名数字 / 评测维度 / 定价对比 / 官方表态 / 政治法规背景 / 团队使用心得等实质信息, 纯"X 模型好强"或梗图式互喷不收
- 即将发布的模型家族预告类速报 (例: "关于明天即将到来的 GPT 5.6 家族") 加分, 尤其带时间点 + 家族命名规则 + 预期能力对比
- **模型实测懒人包 / 多模型横向对照 (例: Codex 模型实测懒人包) 加分** — 要有实际跑过的结论与适用场景分流, 不是转述官方 benchmark
- 模型 / 影片生成 / 多模态背后"技术分歧"类深度拆解加分 — 不是只贴产品名, 而是讲清楚技术决策; 评测标准本身的解读 (例: Agent Arena 偏"任务成功率"而非"听话程度", 对 PM 的提醒) 也加分
- **合规 / 安全机制的原理级解释加分** (例: Anthropic 的 Thariq 撰文解释 Claude 输出文字浮水印为何为 EU AI Act 合规而加、对品质与 token 花费无影响) — 注意这与"演讲二手转述"的差别: 这是有本人一手文章 + 转述者讲清原理 / 限制 / 影响, 所以收
- Claude 生态"落地成成品"型新功能加分 (Claude Cowork 登陆手机后台跑 / 示范即学、Claude Tag 让 Slack 变 AI 协作战场、Claude Code 悄悄新增内建 skill、Codex CLI 新增预算管理 / 多代理委派 / 插件体验优化、**Codex Multi Agent V2**、Director Mode Lite 类版本迭代、Agent View 一个画面掌控所有 AI 编码任务型 UX 大改、Claude 5 大金融专用 AI Agent 模板 (华尔街工作流)、**Anthropic 把「初级分析师」整份工作流程打包成免费插件**、`/goal` 长任务功能 Claude Code 跟 Codex 皆推出) — 这类"具体能做什么 / 变了什么 / 覆盖了哪个垂直行业"的功能落地速报稳定加分
- 周报型「本週 AI 大事」「24h AI 整理」如果做到一分钟看完且密度高, 给 star (scps_jia 系列稳定正例); 但若只是无主线的新闻流水帐, 不收
- 多模型 / 多 Agent 协作的工程化思考、Claude vs ChatGPT / Cursor Composer vs Opus / Codex vs Fable 等带对照与数据的讨论, 加分
- MCP server / 开源 Agent 框架 / 官方开源 Skills / 开源 AI 网页自动化工具若说清楚"能做什么 / 跟现有方案差在哪 / 怎么用", 加分; 只贴名字、只贴 GitHub 连结、或只说"装好后推荐先装 X" 不加分
- 大规模整理类 (120+ 文章 + 30+ 论文的 Claude Code 中文神文、Anthropic 官方创始人手册、Google I/O 新产品完整整理、GitHub 周星星榜前 10、OpenAI Codex 官方 52 个使用案例整理) 加分
- AI 交互范式变化视作具备"重新定义 UI / 重新定义记忆"含义的案例, 加分
- 扣分: 纯个人生活、无信息量 meme、硬广 / 营销号转发、纯情绪发言、PM 周报型流水帐、单一工具名词没有"能做什么"
- 与 AI 主题无关 / 弱相关的内容 (政府补助申请、Python 钓鱼网址教程、念书神经元日常、超写实 3D 模型纯展示、iPAS 每日打卡、Suno 素材接案需求、技术书阅读记忆术、旅游照片剪影片、大厂工程文化文与 AI 无直接关联 (例: Meta 的《Capacity Efficiency at Meta》即使是好文, 若跟 AI 没直接关联仍不收)) 不收
- **AI 在其他学科 / 娱乐领域的泛科普速报 (例: "Claude 开始自己设计蛋白质了"、AI 影片创作比赛 17.5 万美元奖金) 降权** — 缺少工程落地细节或方法论时只是猎奇新闻; 除非讲清模型 / 工具链 / 可复用的工作流
- **个人职涯 / 活动经历类 (面试 AI Engineer 心得、参加 OpenAI 黑客松进决赛、自己做的 SKILL 被老外转载的惊喜贴) 不收** — 属于个人动态而非可迁移的观察; 除非带明确的技术拆解或面试题 / 评审标准级别的信息
- 同主题霸屏内容 (例如 ChatGPT Images 各种切片、同一波 Fable 5 复活的不同人转述、同一波 CLAUDE.md 爆红的不同人转述、**同一波「额度重置 / 限额延长」被多个账号同日刷屏的各种版本**、同一个 Anthropic 工程师 (例 Thariq Shihipar) 演讲被不同人转述的多个版本) 收一条信息量最高的代表即可, 重复扣分. 特别注意"AI 大厂工程师人物型演讲 / 思考分享"若只是二手转述心得无本人一手连结 + 无深度消化, 即使主角是 Anthropic / OpenAI 核心工程师也不豁免降权
- **厂商互喷 / 排队对比梗图型短帖 (例: "Anthropic 延长 / GPT 明天发 / xAI 昨天推 / Gemini 🤓"、"Grok 不靠谱 = 垃圾, Cursor 没模型 = 垃圾, 两个加起来王炸")、以及作者自称"纯闲聊, 无任何知识含量"的帖子, 一律降权**
- 标题党搬运型新闻 (没有作者自己的分析或一手验证) 降权 (例: "Stripe 给 AI agent 装上金融技能"纯产品搬运、TeraWulf 20 年 190 亿算力合约纯合同公告、whaleagent "连最爱嘴的对手都公开认输了"型科技新闻标题党无本文); 学术论文复述但只贴 abstract 无消化也降权 (例: HF 今日第一名某论文图工具的发散感想); 但若是带数据 / 实验细节的 harness 论文消化型分析, 加分
- "我用 Claude Code 做了 X" 类炫耀贴: 必须有清晰的能力清单 / 数据 / 工作流, 否则降权 (**"我用 Claude Code 开发的第一个专案"、"顺手做了个快速打开 repo 的小工具"、"毫无资工背景的人也做出来了" 都属典型降权对象**)
- 故弄玄虚开头 + 没干货、纯连结无文字摘要 (含纯 GitHub / youtu.be 连结)、"深入產業"类极短无内容贴 降权
- 个人抱怨 / 心情贴降权 (**例: "我的 Claude 被封, 申诉也失败回不来了"、"用 AI 做简报改到怀疑人生"、"我开了 X 会员但 Grok 用得很少"**); 但若带具体 token 数据 + 工作流改造方案, 可酌情留
- 假"补充"实际无新内容、"X 天打卡" 流水帐、"Day 47/100" / "Day 145 逐字稿" 类日更打卡型即使内容涉及 AI, 只要是日更序列的一环无独立结论也不收 — 与"续集型协作 N 个月心得"归为同类打卡文化, 降权
- "Claude / ChatGPT 价格 / 额度该不该买" 的纯主观问答、"Claude code -p 有额度可以领" 类极短公告, 信息密度太低不收
- 偏"AI 新手入门心法"、"AI 教学行銷人 8 个实战用法"、"AI 新手不要再从『我要学哪个工具』开始"、"你可以不太会用 AI"、"我不是工程师" 这类心法总论 / 门槛安慰文 不收 — 我们要的是从业者一手观察, 不是教学营销
- 续集型 "协作第 N 个月心得" 但只是流水帐回顾、没新结论 / 新工作流, 降权 (dorgon.chang 协作第 5 个月心得为典型例子)
- 人物型"AI 大厂工程师超狂演讲 / 分享他怎么看未知"型转述若无本人第一人称一手内容 + 无转述者的实质消化, 降权 (例: meicy321 / isaac_shekht 都在转述 Thariq Shihipar 演讲, 都被 down) — **对照组: cooljerrett 转 Thariq 的浮水印机制文章因为有原文 + 原理/限制/影响拆解而被 up**; 与"官方内部知识管理方式曝光"要区分: 后者是揭方法论细节, 前者是感想式演讲转述
- 接案怀旧叙事型 (例: "接案 3 年、30 个客户") 即使涉及 AI 工具, 若只是回忆无方法论 / 无数据, 不收
- 空泛标题党无本文型 (例: "APP 的好日子不多了"、"很多企业以为:"、"有件事我觉得很值得讲一下"、"最近成日见到人讲:"、"现在 AI 真的越来越强了")、单一 youtu.be 连结无说明, 降权
- 作者信号: 已知研究员 / 开源作者 / 厂商官号 / 长期高质量分析号 (moth.ai / cab_late / vincent.chanw / ar.shek / ci.fullstack / brew.agent / brewbytes.ai / tripleh.ai / krumjahn / darwin7381 / tenten.co / garlia.t / hanamizuki / scps_jia / cyesuta.lee / prompt_case / cooljerrett / danielwchen0 / hei_ai.automation / ryanchou0210 / ray.realms / bing_sunzhi / ekcheungai / alicken / journal_of_digital_narrative / buildthink.ai / hunterest.co / kai_ch_chen / 0xspeter / yrzheee / hydai / et.tang.ai / aiposthub / pm.ai.notes / govin999999 / carllee2077 / sliven0722 / p3nchan / travis_studio_inc / martech_bb / truewatch_hq / unicorn.geai / darrell_tw_ / lucasfutures / will_ai_lab / hao0321_studio / marvinpick / thetechcosmo / charles_tychen / dimensiongiga / ilya.liao / alphasnow_ai / andychuah_here_ / azlife_1224 / lin.smart.psu / oxjimmyo / cyh.289 带架构分析或大厂合作型速报时) 权重更高; 匿名 / 低活账号、纯接案 / 带 utm 追踪连结、SEO 营销号权重低
- **作者信号绝不覆盖单条质量, 且高质量作者的低质量帖同样要 down**: krumjahn 是 CLAUDE.md trending 正例作者, 但纯搬运型 (Stripe AI agent 金融技能) 仍降权; debutai.tw 虽是模型发布号, 但纯商业合约公告 (TeraWulf 190 亿) 仍降权; whaleagent 是 CLAUDE.md 元话题正例作者, 但转科技新闻标题党仍降权; **sliven0722 是 Anthropic 内部知识管理正例作者, 但 AI 影片奖金新闻被 down**; **moth.ai 是功能速报强源, 但同日刷屏的"额度满血复活"被 down**; **will_ai_lab 是 GPT 家族预告正例作者, 但"我的 Claude 被封"抱怨贴被 down**; **yrzheee / et.tang.ai / aiposthub / tripleh.ai 在白名单内, 但闲聊 / 假补充 / 泛科普 / 论文发散帖同样被 down**

## 用户正例特征 (evolve 自动提取)
- **brew.agent 逐版 release notes 仍是压倒性稳定源**: Claude Code 2.1.132 (28 项) / 2.1.140 (13 项) / 2.1.146 (16 项) / 2.1.186 / 2.1.187 / 2.1.193 / 2.1.196 (27 项) / 2.1.198 (32 项) / 2.1.199 (24 项) / 2.1.221 (39 项) 每一版逐版拆解 + Codex CLI 0.142.0 (预算管理 / 多代理委派 / 插件体验优化) — 跨越 5 月到 8 月持续点赞, 无需担心内容重复
- **单指令级微更新 + 官方理由解读 (本轮新增的强信号)**: Claude Code v2.1.218 把 `/code-review` 改成 background subagent 及官方理由 (andychuah_here_)、Claude Code 正式推出 `/design` 让设计跟程式距离缩成一个指令 (prompt_case)、Claude Code 新指令 `/checkup` 帮 AI 编程环境做健检 (moth.ai)
- **细粒度配置 tip**: 使用 Fable 时把子代理预设模型固定为 Opus 而非自动选择 (ilya.liao) — "多数人忽略的一个细节"型实操
- **模型发布 + 定价 / 成本结构**: Anthropic 发布 Claude Opus 5, 价格直接对半砍但能力碾压全场 (tenten.co)、Claude 又升级且把 AI Agent 使用成本压下来 (alphasnow_ai)、Claude Code 週上限增加 50% 全线自动套用 (hao0321_studio)、Anthropic 6/15 规则大地震: 订阅算力限制在"人类盯着萤幕互动", 无人值守工作流被套紧箍咒 (garlia.t)
- **额度 / 限制变化带跨厂对照**: Claude 宣布 Fable 延长 vs OpenAI Tibo 宣布 Codex 暂时移除 5h 限制并重置用量 (cyh.289)
- **算力落到用户能力上的布局速报**: Anthropic 拿下 SpaceX Colossus 1 资料中心全部运算容量, 一个月内上线 300+ MW (超过 22 万颗 NVIDIA GPU), 直接回馈 Claude Pro 与 Max 订阅者 (charles_tychen)
- **Claude / Anthropic 生态"具体功能落地"型速报**: Agent View 一个画面掌控所有 AI 编码任务 (moth.ai)、5 大金融专用 AI Agent 模板 (moth.ai)、Managed Agents 三件套自己进化 / 验收 / 分工 (darwin7381 / moth.ai)、把"初级分析师"整份工作流程打包成免费插件 (dimensiongiga)、Claude Cowork 看你操作一次就永远会做 (prompt_case)、Claude Code 更新默默多了一个内建 skill (darrell_tw_)、Director Mode Lite v1.8 (lucasfutures)、`/goal` 长任务 Claude Code 与 Codex 皆推出 (tenten.co / ar.shek)
- **Codex 侧持续加分**: Codex Multi Agent V2 (prompt_case)、Codex 模型实测懒人包 (azlife_1224)、官方整理 52 个使用案例含 Skill 外挂对照 (cooljerrett)、Codex 正式支援 Chrome 扩充背景平行多分页 (cooljerrett)、让 Codex 回看 30 天 session 找出反覆手动任务的自我提升 prompt (cooljerrett)
- **跨工具编排**: 用 Claude Code 指挥 Codex CLI 的多种方法 (darrell_tw_)
- **合规 / 机制原理拆解 (带本人一手文章)**: Claude 输出加文字浮水印为 EU AI Act 合规, 不影响品质与 token 花费 (cooljerrett 转 Thariq 原文)
- **CLAUDE.md / 设定档反直觉结论**: Claude 5 删掉 80% 规则效果没有变差 (brewbytes.ai)、karpathy 的 CLAUDE.md 冲上 GitHub #1 220K stars 多数人还没读 (ekcheungai)、Anthropic 内部知识管理方式曝光 (sliven0722)
- **争议 / 传言验证**: 传言 Superpowers 会让原本很强的模型变弱 (oxjimmyo)
- **skill 生态榜单**: 本週竄起的 Claude Code skill Top 3 (lin.smart.psu)
- **模型 saga 长线追踪**: Claude Sonnet 5 突发发布 (prompt_case)、Fable 5 / Mythos 5 因美国出口管制被封锁到白宫拟松绑 (truewatch_hq)、Fable 5 重新上线但一般用户可能失望 (unicorn.geai)、GPT 5.6 家族预告 (will_ai_lab)、今天跟团队讨论到 Opus 4.7 (ci.fullstack)
- **跨界合作速报**: SpaceX 与 Claude 宣布合作 (thetechcosmo)
- **开源工具带具体使用场景**: 写自动化测试与网页脚本时发现的开源 AI 网页自动化工具 Midscene (bing_sunzhi)
- **一分钟高密度周报**: 1 分钟带你看完本週 AI 大事 5/4 与 5/18 (scps_jia) — 系列稳定
- **实战工作流案例**: 用 html 审批提案的 AI 团队笔记 (hanamizuki)
- **趋势观察**: 最近 Vibe coding 圈出现一个新趋势 (marvinpick)
- 承继历史正例特征: GitHub Trending 一手榜单速报带异常冲榜信号 (martech_bb DeusData codebase-memory-mcp)、Loop 编排 token 优化实测 (travis_studio_inc)

## 用户负例特征 (evolve 自动提取)
- **AI 跨领域 / 娱乐向泛科普速报无工程细节**: Claude 开始"自己设计蛋白质"了 (aiposthub)、17.5 万美元只为找出谁能用 AI 拍出一段真正"看得完"的故事 (sliven0722) — 后者说明正例作者发猎奇新闻同样被 down
- **个人职涯 / 活动 / 成就动态**: 最近去面试 AI Engineer (daidouofficial)、跟朋友参加 OpenAI 黑客松有幸进入决赛 (data_pythoness)、"三个礼拜前随手做的 SKILL 被老外疯狂转载还留了三个 PR" (dustin_gmat) — 个人动态无可迁移方法论
- **纯连结无任何文字摘要**: 只贴 github.com/ShawnPana/phone-harness (dustin_gmat)、只贴 youtu.be 连结 (chengcheng_tag)
- **同日同主题霸屏 + 厂商互喷梗图型**: 突发! Claude 额度突然"满血复活", Anthropic 无预警重置所有用量限制 (moth.ai)、"Anthropic: Fable 5 不加价延长 / GPT: 明天发布 5.6 / xAI: 昨天推 Grok 4.5 / Gemini: 🤓" (cryptowesearch.backup)、"Grok 不靠谱 = 垃圾, Cursor 没模型 = 垃圾, 加起来王炸" (dingyi)、"纯闲聊, 无任何知识含量"开头的重置时间对齐推测 (viserys0219) — 同一波额度重置话题只保留带跨厂对照 / 结构解读的一条 (cyh.289 被 up), 其余全 down; 注意 moth.ai 是强源但这条仍 down
- **AI 大厂工程师个人演讲 / 思考分享型多人转述 (无第一手连结 + 无转述者消化)**: Thariq Shihipar 的超狂演讲 (meicy321)、Claude Code 工程师 Thariq Shihipar 第一次分享他怎么看待"未知" (isaac_shekht) — 同一位工程师同一场演讲被两个账号转述都被 down; 对照 cooljerrett 转 Thariq 浮水印原文被 up, 关键在有原文 + 有实质拆解
- **纯商业合约 / 算力供应长约新闻公告 (无分析、无对用户的影响)**: TeraWulf 拿下 Anthropic 20 年算力长约 190 亿美元 (debutai.tw) — 与 charles_tychen 的 SpaceX Colossus 算力速报 (被 up) 形成对照: 后者讲清楚"直接回馈 Pro / Max 订阅者"
- **HN / 外站热帖二手搬运**: "今日 Hacker News 爆红: 开发者正在发动一场拒绝财务刺客的本地独立革命" (a5555555678) — 我们已有独立 hackernews 源, 二手转述重复覆盖
- **"我用 Claude Code 做了 X" 但只晒成果没讲 workflow**: 这是我用 Claude Code 开发的第一个专案 (x.801059)、顺手做了个快速打开 repo 的小工具 (walkccc)、"谁敢信⋯⋯我一个毫无资工背景的人" (chens.corn)
- **个人抱怨 / 心情 / 使用偏好闲聊**: 我的 Claude 被封申诉也失败回不来了 (will_ai_lab, 正例作者也不豁免)、用 AI 做简报真的会改到怀疑人生 (webbrrlo)、我开了 X 会员但 Grok 用得很少 (yrzheee)、前阵子去德国旅游拍了一堆照片想剪纪录影片 (0x0funky)、昨天打开交接同事的资料夹差点昏倒 (sparkroom22)
- **空泛标题党 / 感叹无本文**: 深入產業 (wan_hetalia)、很多企业以为: (alicken)、APP 的好日子不多了 (polyglot.tw_terry)、1/4 (wilsonhuangxyz)、连最爱嘴的对手都公开认输了 (whaleagent)、有件事我觉得很值得讲一下—— (rock.ai.w7)、最近成日见到人讲: (ericleung.hk)、现在 AI 真的越来越强了 (dsif2017)
- **AI 新手心法 / 门槛安慰 / SEO 教学文**: AI 新手不要再从"我要学哪个工具"开始 (hanlinhans)、Claude 教学 2026 行销人 8 个实战用法 (seo.whoops)、你可以不太会用 AI (mkt_girleat)、我不是工程师 (yunghsinw)
- **日更打卡型即使涉及 AI 也不收**: Day 47/100 (answer00125)、Day 145 逐字稿不要直接拿来用 / Day 140 跟 AI 一起用同一台 Mac (andrew54068)、iPAS 应用规划师每日挑战 Day 333 (nickai216)
- **续集型协作 N 个月心得流水帐**: 接续上一篇跟 agent 协作第 5 个月的心得 (dorgon.chang)
- **假"补充"实际无新内容**: 刚刚 vibe coding 可能不知道的 5 件事补充版 (et.tang.ai)
- **只列工具名没说用途**: 装好后推荐先安装这几个 Skill (goodbruce1)
- **大厂工程文化深度文若跟 AI 无直接关联**: Meta《Capacity Efficiency at Meta》(kojenchieh)
- **接案怀旧叙事 / 接案询价**: 接案 3 年、30 个客户 (awoo_gw)、做音乐制作常需要大量 Suno 素材 (romanticamaj)
- **标题党搬运型新闻缺少一手分析**: Stripe 刚给 AI agent 装上一套金融技能 (krumjahn)
- **论文截图 + 抽象发散但没自己消化**: 看完 HF 今日第 1 名 Crafter 我反而觉得麻烦在另一段 (tripleh.ai)
- **纯主观价格问答**: 今日 claude 和 chatgpt plus / pro 的价格, pro 10 多个人够用吗 (walking1153)
- **与 AI 弱相关或无关**: 技术书阅读记忆术 (fennyhsu1936)、台湾每年上百种政府补助可以申请 (sally.sales.ttt)、Python 钓鱼网址与钓鱼网站补充 (wisdom701021)、念书念到 ca3 神经元 (ddmmbb45)、超写实 3D 模型纯展示 (magicmonx)、不会剪片不会画图又想留下生活小瞬间 (dz_270k)
- 承继历史负例特征: "Google 400 亿押注 Anthropic" / "OpenAI 重新定义手机 联发科 Qualcomm 供应链" 纯合约供应链公告、ChatGPT Images 各种切片同主题霸屏、"Claude code -p 有额度可以领" 极短公告、纯开源数据炫耀 (DeepTutor 111 天 20k stars) 没说工具好在哪
