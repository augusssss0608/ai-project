---
source_id: threads
label: Threads (For You)
updated_by: evolve_v8
last_evolve_at: "2026-07-10T15:26:00+09:00"
evolve_count: 8
---

# Threads For You 偏好

## 核心判断维度
- 优先: AI 研究员 / 从业者的一手观察、模型发布与使用心得、工具 / SDK 新功能、争议性观点、跨界专家 (学者 / 数学家) 谈 AI
- 重点关注 Claude / Codex / Anthropic / OpenAI / Google DeepMind / DeepSeek 生态的深度更新 (新指令 / 新功能 / 算力布局 / Agent 模板 / 官方插件 / 版本 release notes / 用量上限 / 计费模型变化 / 官方手册 / 记忆系统架构翻新 / Dynamic Workflows 类工作流范式 / 手机后台跑 Agent / Slack 内嵌 Claude Tag / 内建 skill 新增)
- Claude Code / Codex / Cursor / Antigravity 类 AI coding 工具的工程化议题尤其加分: Agent View、Agent harness、Harness Engineering 方法论、subagent 成本与选型、Skills guide、Agent SDK 计费、week limit 调整、`/goal` 自主开发与长任务、auto mode / `/usage` 用量拆解 / `/code-review` 类新内建指令、权限控制 + skills + 多层 `.claude` 专案设定、Goal / 终点条件类自动化机制、Chrome 扩充背景多分页、施工日誌 prompt (边写边记决策点)、Claude Agent SDK ↔ Codex 跨平台跳槽心得、Codex 自我提升 prompt (回看 30 天 session 找重复手动操作)、Skill 自我改进循环 (根据反馈自动改进自己)、Loop 编排的 token 消耗优化实测
- **Claude Code / Codex 逐版 release notes 拆解是最稳定的高频正例 (brew.agent 源)**: Claude Code 2.1.x 每一版 (186 / 187 / 193 / 196 / 198 / 199) + Codex CLI 0.14x (预算管理 / 多代理委派 / 插件体验优化) 每次都收. 只要标题说清"这版 N 项 CLI 变更"型逐版拆解, 即使版本号密集也要保留 — 这是用户明确高频点赞的稳定源. 无需担心霸屏, brew.agent 逐版列表本身就是核心信号
- AI coding 成本 / 部署判断信号 (例: 微软给员工试用 Claude Code 六个月后砍掉的成本訊號、Copilot 改量计费实测、Anthropic 计费大地震、Agent SDK & `claude -p` 改 credit 计价、"顶尖 AI 正在变成奢侈品"的定价反思) 优先 — 这类"商业行为背后揭示的真实成本结构"比单纯排行榜更值得收
- **但纯商业合约 / 算力供应长约 / 财报数字公告 (例: TeraWulf 拿下 Anthropic 20 年算力長約 190 亿美元、Google 400 亿押注 Anthropic、"OpenAI 联发科 Qualcomm 供应链") 只是新闻搬运型报导, 无作者分析或成本结构解读, 降权** — 与上一条"成本反思分析"要区分开: 前者只是数字公告, 后者带商业结构洞察
- CLAUDE.md / 设定档 / repo 内项目知识管理类爆款加分 — 反映"AI 时代项目背景知识如何沉淀"的元话题; 尤其带反直觉结论 (例: "设定档越长越强? 刚好相反"、karpathy CLAUDE.md 冲上 GitHub Trending #1) 更加分. Anthropic / OpenAI 官方内部知识管理方式曝光型 (例: sliven0722 揭 Anthropic 内部知识管理) 也加分
- GitHub Trending #1 / 前几名异常信号类速报 (headroom、Understand Anything 59.2k stars、karpathy CLAUDE.md 220K stars、DeusData codebase-memory-mcp 一路狂飙 +7,674 星冲到 17.8k) 加分 — 用户持续点赞"今天 GitHub Trending 第 X 名是 Y"型一手榜单观察 (tripleh.ai / govin999999 / martech_bb); 关键是"带异常冲榜信号 + 项目能做什么"
- 实战工作流值得加分: Dynamic Workflows / Claude Code workflows 改变写 code 方式的实测、SDD / MCP / Agent Canvas / Browser-use / Hermes Agent / self-improvement loop / Dreaming / Managed Agents 三件套 / Claude Code 做完整 app 的端到端案例 / Claude Code + MCP 组合工作流 / 用 html 审批提案 / Vibe Marketing 实际案例 / Midscene 类 AI 网页自动化开源工具 / Loop 编排省 token 实测 (要看到落地链路 + 设计取舍 + 跟现有方案差在哪, 不只是点名工具)
- 元思考与行业洞察类好文 (例: "95% 自动化不算自动化"、"Token = 钱"、"单线程 vs 多线程 AI"、"不是比 prompt 写得漂亮"、"如果你还在研究怎么写 Prompt 可能已落后下一阶段"、"Agent Engineering = SE 变形"、"AI coding 进入 usage ceiling 竞争"、"Anthropic 做的已经不是聊天 AI"、"现在 AI 的价值不是完全服从而是能帮你完成任务") 优先, 哪怕作者不知名
- 商业模式 / 算力结构分析 / 产业链 / 计费 / 流量变化 (Copilot 量计费 +10x 实测、Cloudflare 在 AI 时代收"过路费"的护城河分析、Agent SDK 改 Credit、Claude 周用量 +50%、Anthropic 计费规则大地震、5h limit token 体感数据、AI 导流洗牌带数据的流量结构分析) 优先; 但要有"作者自己的结构性分析", 不是单纯合约金额公告
- **模型发布 / 排名 / 暂停复活 / 出口管制封锁的连续追踪是用户高频正例** (例: Claude Opus 4.8、Claude Sonnet 5 发布、Claude Fable 5 / Mythos 5 在 Arena.ai 三榜夺第一 → 因美国出口管制被 Anthropic 无预警封锁 → 白宫拟松绑 → 高层松口"数日内"重新开放 → 重新上线但一般用户可能失望) — 同一模型 saga 的关键节点都收, 但要带排名数字 / 评测维度 / 官方表态 / 政治法规背景等实质信息, 纯"X 模型好强"不收
- 即将发布的模型家族预告类速报 (例: "关于明天即将到来的 GPT 5.6 家族") 加分, 尤其带时间点 + 家族命名规则 + 预期能力对比
- 模型 / 影片生成 / 多模态背后"技术分歧"类深度拆解加分 — 不是只贴产品名, 而是讲清楚技术决策; 评测标准本身的解读 (例: Agent Arena 偏"任务成功率"而非"听话程度", 对 PM 的提醒) 也加分
- Claude 生态"落地成成品"型新功能加分 (Claude Cowork 登陆手机后台跑、Claude Tag 让 Slack 变 AI 协作战场、Claude Code 悄悄新增内建 skill、Codex CLI 新增预算管理 / 多代理委派 / 插件体验优化、Director Mode Lite 类版本迭代) — 这类"具体能做什么 / 变了什么"的功能落地速报稳定加分
- 周报型「本週 AI 大事」「24h AI 整理」如果做到一分钟看完且密度高, 给 star (scps_jia 系列稳定正例); 但若只是无主线的新闻流水帐, 不收
- 多模型 / 多 Agent 协作的工程化思考、Claude vs ChatGPT / Cursor Composer vs Opus / Codex vs Fable 等带对照与数据的讨论, 加分
- MCP server / 开源 Agent 框架 / 官方开源 Skills / 开源 AI 网页自动化工具若说清楚"能做什么 / 跟现有方案差在哪 / 怎么用", 加分; 只贴名字或只说"装好后推荐先装 X" 不加分
- 大规模整理类 (120+ 文章 + 30+ 论文的 Claude Code 中文神文、Anthropic 官方创始人手册、Google I/O 新产品完整整理、GitHub 周星星榜前 10) 加分
- AI 交互范式变化视作具备"重新定义 UI / 重新定义记忆"含义的案例, 加分
- 扣分: 纯个人生活、无信息量 meme、硬广 / 营销号转发、纯情绪发言、PM 周报型流水帐、单一工具名词没有"能做什么"
- 与 AI 主题无关 / 弱相关的内容 (政府补助申请、Python 钓鱼网址教程、念书神经元日常、超写实 3D 模型纯展示、iPAS 每日打卡、Suno 素材接案需求、技术书阅读记忆术) 不收
- 同主题霸屏内容 (例如 ChatGPT Images 各种切片、同一波 Fable 5 复活的不同人转述、同一波 CLAUDE.md 爆红的不同人转述、**同一个 Anthropic 工程师 (例 Thariq Shihipar) 演讲被不同人转述的多个版本**) 收一条信息量最高的代表即可, 重复扣分. 特别注意"AI 大厂工程师人物型演讲 / 思考分享"若只是二手转述心得无本人一手连结 + 无深度消化, 即使主角是 Anthropic / OpenAI 核心工程师也不豁免降权
- 标题党搬运型新闻 (没有作者自己的分析或一手验证) 降权 (例: "Stripe 给 AI agent 装上金融技能"纯产品搬运、TeraWulf 20 年 190 亿算力合约纯合同公告); 学术论文复述但只贴 abstract 无消化也降权 (例: HF 今日第一名某论文图工具的发散感想); 但若是带数据 / 实验细节的 harness 论文消化型分析, 加分
- "我用 Claude Code 做了 X" 类炫耀贴: 必须有清晰的能力清单 / 数据 / 工作流, 否则降权
- 故弄玄虚开头 + 没干货、纯连结无文字摘要、"深入產業"类极短无内容贴 降权
- 个人抱怨 / 心情贴降权; 但若带具体 token 数据 + 工作流改造方案, 可酌情留
- 假"补充"实际无新内容、"X 天打卡" 流水帐 不收
- "Claude / ChatGPT 价格 / 额度该不该买" 的纯主观问答、"Claude code -p 有额度可以领" 类极短公告, 信息密度太低不收
- 偏"AI 新手入门心法"、"AI 教学行銷人 8 个实战用法" 这类面向初学者的总论 / SEO 文不收 — 我们要的是从业者一手观察, 不是教学营销
- 续集型 "协作第 N 个月心得" 但只是流水帐回顾、没新结论 / 新工作流, 降权
- 大厂工程文化深度文若跟 AI 无直接关联, 不收
- **人物型"AI 大厂工程师超狂演讲 / 分享他怎么看未知"型转述若无本人第一人称一手内容 + 无转述者的实质消化, 降权** (例: meicy321 / isaac_shekht 都在转述 Thariq Shihipar 演讲, 都被 down) — 与"官方内部知识管理方式曝光"要区分: 后者是揭方法论细节, 前者是感想式演讲转述
- 作者信号: 已知研究员 / 开源作者 / 厂商官号 / 长期高质量分析号 (moth.ai / cab_late / vincent.chanw / ar.shek / ci.fullstack / brew.agent / tripleh.ai / krumjahn / darwin7381 / tenten.co / garlia.t / hanamizuki / scps_jia / cyesuta.lee / prompt_case / cooljerrett / danielwchen0 / hei_ai.automation / ryanchou0210 / ray.realms / bing_sunzhi / ekcheungai / alicken / journal_of_digital_narrative / buildthink.ai / hunterest.co / kai_ch_chen / 0xspeter / yrzheee / hydai / et.tang.ai / aiposthub / pm.ai.notes / govin999999 / carllee2077 / sliven0722 / p3nchan / travis_studio_inc / martech_bb / truewatch_hq / unicorn.geai / darrell_tw_ / lucasfutures / will_ai_lab 带架构分析时) 权重更高; 匿名 / 低活账号、纯接案 / 带 utm 追踪连结、SEO 营销号权重低. 注意作者信号不覆盖单条质量: krumjahn 早先是 CLAUDE.md trending 正例作者, 但其纯搬运型 (Stripe AI agent 金融技能) 仍降权; debutai.tw 虽 label 显示为模型发布号, 但纯商业合约公告 (TeraWulf 190 亿) 仍降权

## 用户正例特征 (evolve 自动提取)
- **brew.agent 逐版 release notes 是压倒性稳定源 (最近 2 周独立占 6 条正例)**: Claude Code 2.1.186 (33 项 CLI 变更) / 2.1.187 (21 项) / 2.1.193 (15 项) / 2.1.196 (27 项) / 2.1.198 (32 项) / 2.1.199 (24 项) 每一版逐版拆解 + Codex CLI 0.142.0 (4 项重要更新 涵盖预算管理 / 多代理委派 / 插件体验优化) — 高频稳定正例, 无需担心内容重复
- Claude / Anthropic 模型 saga 长线追踪: Claude Sonnet 5 突发正式推出 (prompt_case)、Fable 5 / Mythos 5 因美国出口管制被 Anthropic 突然无预警封锁 + 白宫拟松绑最快下周重新开放 (truewatch_hq)、Claude Fable 5 今天重新上线但一般用户可能会失望 (unicorn.geai)、Anthropic 高层松口 Fable 5 可望数日内重新开放 (moth.ai)
- Anthropic / Claude 生态"具体功能落地"型速报: Claude Cowork 即将登陆手机关掉 App 也照跑 (moth.ai)、Claude Tag 来了 Slack 真的要变成 AI 协作战场 (aiposthub)、Claude Code 更新默默多了一个内建 skill (darrell_tw_)、Codex CLI 0.142.0 带来预算管理 + 多代理委派 + 插件体验优化 (brew.agent)
- 模型家族预告类速报: 关于明天即将到来的 GPT 5.6 家族 (will_ai_lab)
- 工程效率实测 / token 消耗优化: 这样跑 Loop 能省下大半的 token 消耗 (travis_studio_inc)
- 官方内部知识管理曝光: Anthropic 內部的知識管理方式曝光 (sliven0722)
- GitHub Trending 一手榜单速报 (带异常冲榜信号 + 项目能做什么): 本週 GitHub trending 第 2 名 DeusData 的 codebase-memory-mcp 一路狂飆 +7,674 星衝到 17.8k (martech_bb)
- 版本迭代速报 (第三方工具): Director Mode Lite v1.8 发布 (lucasfutures)
- 承继历史正例特征: Claude Code 逐版 release notes 拆解 (brew.agent / tripleh.ai)、Dynamic Workflows 类工作流范式 (et.tang.ai / 7xuan.lu)、AI coding 定价结构反思 (p3nchan / hydai / 7evenguy_trade)、CLAUDE.md 元话题 (whaleagent)、Harness / Skill 自我改进循环 (yrzheee)、Codex 重磅更新与对照 (prompt_case)、一分钟密度型周报 (scps_jia)

## 用户负例特征 (evolve 自动提取)
- **纯商业合约 / 算力供应长约新闻公告 (无作者分析或成本结构解读)**: TeraWulf 拿下 Anthropic 20 年算力长约 190 亿美元合约收入落袋 (debutai.tw) — 属于纯合同数字公告型报导, 与"AI coding 成本反思 / 定价结构分析"要区分开; debutai.tw 虽是模型速报号但这类纯商务合约公告被 down
- **AI 大厂工程师个人演讲 / 思考分享型多人转述 (无第一手连结 + 无转述者消化)**: Anthropic 技术工程师 Thariq Shihipar 的超狂演讲 (meicy321)、四天前 Claude Code 的工程师 Thariq Shihipar 第一次分享他在 AI 世代裡怎么看待"未知" (isaac_shekht) — 同一位工程师同一场演讲被两个不同账号转述都被 down, 说明"人物型演讲思考分享"若只是感想式二手转述, 即使主角是 Anthropic 核心工程师也不豁免降权. 关键: 若能贴出本人原始连结 + 有实质思考消化则例外
- 与 AI 弱相关或无关的内容: 阅读记忆术、政府补助申请整理、Python 钓鱼网址教程、iPAS 每日挑战打卡、念书 ca3 神经元、超写实 3D 模型纯展示、Meta 工程文化文跟 AI 无直接关联、Suno 音樂素材接案询问
- 标题党 / 搬运型新闻缺少一手分析: "Stripe 刚给 AI agent 装上一套金融技能" 纯产品搬运无作者验证 (krumjahn)、"Google 400 亿押注 Anthropic"、"OpenAI 重新定义手机, 联发科 Qualcomm 供应链"
- 论文截图 + 抽象发散但没自己消化: "看完 HF 今日第 1 名 Crafter, 我反而觉得麻烦在另一段" 论文图工具的发散感想信息密度低 (tripleh.ai)
- 极短无内容 / 故弄玄虚开头: "深入產業" 单词贴、youtu.be 单连结无说明、"1/4" 类极短开篇没后文、"最近成日見到人講" 没下文
- AI 教学 / 初学者总论 / SEO 营销文: "Claude 教學 2026: 行銷人 8 個實戰用法"、"AI 新手不要再從『我要學哪個工具』開始" 类心法文
- 接案询价 / 业配 / 纯营销号转发 (常带 utm): "脆友詢價"、image-to-video 广告、"不會剪片不會畫圖怎麼辦" 营销话术、"接案 3 年 30 個客戶" 怀旧叙事无方法论
- 浅层情绪感想 / 抱怨没有具体场景或对比: "Claude 简直太棒"、"太好了😍"、"GPT 生成的图片可以直接改了"、"现在 AI 真的越來越強了"、"用 AI 做簡報改到懷疑人生"、"Claude 被封申訴失敗"、"X 会员 Grok 用得少"
- 重复的 ChatGPT Images / GPT Image 2 生图功能切片, 同主题霸屏多条
- 续集型流水帐 / 打卡日記: "Day 47/100"、"Day 145 逐字稿"、"跟 agent 協作第 5 個月的心得" 续集回顾但无新结论
- PM 周报 / 个人随笔流水帐: "台積電 PM 第 31 週週報"、"我做了一件很奇怪的事"、"昨天打開交接同事的資料夾差點昏倒"
- 工具名词出现但没说能做什么: 单句 "GA4 接上 MCP"、单介 "MinerU 把 PDF 变成 AI 可读"、"裝好後推薦先安裝這幾個 Skill" 极短工具点名
- "24 小时新闻统整" 但密度低无主线、"为了选对 AI 工具" 空泛标题
- 假"补充" / 假"追加" 实际无新内容
- 纯开源数据炫耀 (例: DeepTutor 111 天 20k stars) 没说工具好在哪 / 怎么用 — 注意与 GitHub Trending #1 / #2 一手速报区别: 后者带"今天异常冲榜"信号 + 项目能做什么, 前者只晒数字
- "我用 Claude Code 做了 X" 但只晒成果没讲 workflow / 验证: "毫無資工背景的人也能做到" 励志炫耀、"用 Claude Code 開發的第一個專案"、"vibe coding 做了一个快速打开 repo 小工具"
- 极短公告型 / 转手抄: "Claude code -p 有额度可以领"、"今日 Claude / ChatGPT 价格大佬聊聊" 类问答
