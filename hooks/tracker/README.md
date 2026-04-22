# Claude Code Usage Stats 系统使用说明

> 本地运行的 Claude Code 使用统计 dashboard。目的是**降低每次 session 的 baseline token 消耗**，通过识别和禁用冷藏的 skill / subagent / CLAUDE.md 章节来实现。
>
> 这份文档既是给用户看的使用手册，也是给未来 Claude Code session 恢复上下文用的。

---

## 0. 给未来 Session 的 1 页快速摘要

**读完这一节，你就能接手这个系统。**

### 这是什么
- 本地 Python http server (38080 端口) + SQLite + vanilla JS/CSS 的使用统计 dashboard
- 通过 PostToolUse hook 采集 Claude Code 工具调用事件
- 目的：识别 0 触发的装饰品 skill/subagent/规则，降低 token baseline

### 数据存哪
- `~/.claude/usage-stats/events.db` — **SQLite 真理源**，所有查询读这个
- `~/.claude/usage-stats/events.jsonl` — 纯备份
- `~/.claude/usage-stats/tracker-errors.log` — hook 错误日志
- `~/.claude/usage-stats/archive-log.jsonl` — 禁用/恢复审计

### 代码在哪（v8 已拆 5 个 Python 模组, 全部 ≤1200 行）
- `~/.claude/hooks/usage-tracker.sh` — PostToolUse hook
- `~/.claude/hooks/usage-web.py` — **411 行** — HTTP Handler + archive/restore + security + main() 薄壳
- `~/.claude/hooks/usage_web_core.py` — **622 行** — 常量 (LABELS/EVENT_TYPES/COLD_SECTIONS) + 原子 helpers + list_* + tiktoken
- `~/.claude/hooks/usage_web_queries.py` — **773 行** — SQL 查询全家桶 + 分析 (analyze_claude_md / compute_prune_score / compute_cold_items / query_* 家族)
- `~/.claude/hooks/usage_web_render.py` — **1192 行** — 渲染 helpers + 所有 `_render_*` + flip 卡背面 + `render()` orchestrator
- `~/.claude/hooks/usage_web_summary.py` — **222 行** — AI 摘要 + 配额 + cache + dedup + claude CLI 子进程
- `~/.claude/hooks/usage-web.css` — 前端样式（~1540 行，设计 token + 稳定骨架 + flip card + sheet 抽屉 + 霓虹绿 cyberpunk）
- `~/.claude/hooks/usage-web.js` — 前端交互（~600 行，flip / sheet / tooltip / summary fetch / copy path）
- `~/.claude/hooks/usage-report.sh` — CLI 报告
- `~/.claude/hooks/usage-archive-cold.sh` — 批量禁用 CLI
- `~/.claude/hooks/usage-rebuild-db.sh` — 灾备重建

**依赖线性**: `core → queries → render → main`（无循环）, `summary` 独立无依赖。

### 前端结构（v7 方案 C + v8 cyberpunk + flip card）
- **稳定骨架**：`page-header`（H1 + summary meter）+ sticky `tab-bar` 永不随 tab 变动
- **4 个自包含 tab**：总览 / 工具使用 / 上下文 / 记忆 — 每个 tab 自带所需控件
- **tab 切换**：grid `1fr` 让 `.tab-viewport` 自动吃满 `.page { min-height:100vh/100dvh }`；`tabEnter` keyframes 单次播放不抖；切 tab 自动复原所有翻面卡
- **Neo-Terminal 荧光绿主题**：`#39ff14` 霓虹绿 + Chakra Petch display + JetBrains Mono + 雙色霓虹暈 + CRT 掃描線 overlay
- **Card flip (v8)**：所有卡片整体可点翻面, 3D Y-rotate 420ms；grid `grid-template-areas:"face"` 让 front/back 同格自动取 max-height 避免滚动；无上限同时翻；filter/tab 切换自动复原
- **7 类卡片背面**：
  - Hero (4 卡)：窗口对比 / type 分布 / session 明细 / 近 12 个月柱状
  - Today (per owner)：30 天趋势 + type 拆分 + 跳转 usage
  - Health (per subproject)：24h 趋势 + 错误日志 + 空窗时长
  - Active (per etype)：30 天趋势 + 覆盖率 + owner 分布条 + 配对率 + token 回收估算
  - Cold (per 分类)：已禁用进度 + 批量禁用按钮
  - CLAUDE.md (per file)：token 分布 + 复制可删减清单按钮
  - Memory：**不用 flip, 用 sheet 抽屉**（右上角 `统计` 按钮 → 右侧滑入）
  - Compact：纯列表时间轴，无统计入口（无 flip、无 sheet）
- **设计 token**：6 档 spacing (4/8/12/16/24/32)、3 档 radius (2/3/14)、6 组 typography、卡片材质 `--card-bg` 渐变 + `--shadow-card` 多层阴影

### 安全模型（必须准确理解，我之前写错过）

| 端点 | 方法 | 可通过 tunnel 访问吗 | 说明 |
|---|---|---|---|
| `GET /` `/style.css` `/app.js` `/mock` | GET | ✅ | 纯读 |
| **`GET /open?path=...`** | GET | ✅ **会触发 Mac 本地 `open`** | 白名单路径检查 + 无本机直连限制 |
| `GET /summary?path=...` | GET | ✅ | 白名单检查 + 配额节流 + 并发去重, 返回 AI 中文摘要 (子进程 `claude -p`) |
| `GET /summary-status` | GET | ✅ | 返回今日配额/cache size/pending |
| `GET /prune-list?path=...` | GET | ✅ | 返回高删减收益 section 的 markdown 清单 |
| `POST /archive` / `POST /restore` / `POST /clear-summary-cache` | POST | ❌ 403 | 检查 `cf-ray / cf-connecting-ip / cf-ipcountry / cdn-loop` header，tunnel 拒绝。**写操作只能本机直连** |

### 最关键的不要做

1. **不要加 Session drill-down / 日志浏览器** — 边界失控
2. **不要加 memory/skill 网页编辑器** — 写操作引入并发覆盖风险
3. **不要加 LLM 评分 CLAUDE.md** — Codex 明确警告是最大陷阱
4. **不要加"一键执行"类按钮**（build/test/proto sync）— 执行长任务会失控
5. **不要记录 Bash/Edit/Write 事件** — mission creep
6. **CLAUDE.md 不要 auto-cut** — 只标记不自动删
7. **已禁用的 skill 是 mv 到 `.disabled/`，不是删除** — 可逆
8. **Claude Code 启动时扫 `skills/*/SKILL.md` 和 `agents/*.md`，不扫 `.disabled/`**，这是禁用机制的核心

### 关键约定
- **zero-deps 原则**：运行时 Python stdlib + vanilla JS/CSS；**分析层允许可选 `tiktoken`**（fallback 到 bytes/3.5）
- **AI 摘要是例外**：需要本地有 `claude` CLI (订阅制 auth), 走子进程 `claude -p` 不占 API key. 无 CLI 时 `/summary` 返回错误, dashboard 其余功能照常
- **子 agent 内部的 tool 调用也被捕获**，共享父 session_id
- **Owner 标签** 由 `compute_owner(path)` 从路径推导，见 §6
- **Cold 检测** = 文件系统枚举 MINUS 事件触发（不是缺数据推导）
- **ThreadingHTTPServer**：每请求一 daemon 线程, 避免 `claude -p` 长子进程阻塞其他请求

### 有哪些延后/观察项
见 §11 TODO 清单。核心原则：**Codex 否决的项永远不做**。

---

## 1. 核心目的

1. **统计 Claude Code 工作流使用情况**：哪些 skill / subagent / 规则文件被真正用了
2. **识别装饰品**：30+ 天 0 触发的资源，建议禁用或删除
3. **降低 token baseline**：每次 Claude Code 启动 session 会自动加载 skill 列表 + CLAUDE.md + memory，装饰品越多，baseline token 越大
4. **反向检测过度设计**：用数据证明"我装了这么多 skill 实际上用了多少"

**一句话**：这是一个本地跑的 dashboard，告诉你哪些 Claude Code 资源是真用、哪些是装饰，给你依据做 token 优化。

---

## 2. 文件清单

所有文件都在 `~/.claude/hooks/` 和 `~/.claude/usage-stats/` 下。

### 脚本/代码（`~/.claude/hooks/`）

| 文件 | 角色 | 说明 |
|---|---|---|
| `usage-tracker.sh` | **事件采集** hook | 挂在 PostToolUse，每次工具调用都触发，双写 jsonl + sqlite |
| `usage-web.py` | **Web dashboard 后端** | Python stdlib 的 http.server，渲染 HTML，提供 /open / /archive / /restore 端点 |
| `usage-web.css` | **前端样式** | 暗色主题 + 所有布局 + 动画 + 响应式断点 |
| `usage-web.js` | **前端交互** | count-up / owner 筛选 / 展开收起 / 禁用启用按钮 |
| `usage-report.sh` | **CLI 报告** | 命令行查询 events.db 输出文本排行，和 dashboard 数据一致 |
| `usage-archive-cold.sh` | **冷藏禁用 CLI** | 批量把冷藏 skill/subagent 移到 `.disabled/`，支持 dry-run / restore / list |
| `usage-rebuild-db.sh` | **灾备重建** | 用 jsonl 重建 sqlite（只在 sqlite 损坏时用，会丢 sqlite-only 事件） |
| `USAGE-STATS.md` | **本文档** | 给用户 + 未来 session 看的说明 |

### 数据（`~/.claude/usage-stats/`）

| 文件 | 说明 |
|---|---|
| `events.db` | **SQLite，统计真理源** — dashboard / report / 所有查询都读这个 |
| `events.jsonl` | **jsonl，纯备份** — tracker 双写一份，用于灾备重建 |
| `tracker-errors.log` | **错误日志** — hook 内部失败时写入（sqlite 写失败 / jsonl 写失败 / schema init 失败） |
| `archive-log.jsonl` | **禁用/恢复审计日志** — 每次 archive 或 restore 都记录 ts + type + name + src + dst |

---

## 3. 快速开始

### 3.1 本机访问

```bash
# 启动 dashboard（如果没自动起）
nohup python3 ~/.claude/hooks/usage-web.py > /tmp/usage-web.log 2>&1 &

# 浏览器打开
open http://localhost:38080
```

**自动启动**：`~/.zshrc` 已配置开终端时自动启动 dashboard（如果没在跑），下次开终端会自动 up。

### 3.2 手机远程访问

Dashboard 通过 `cloudflared tunnel` 暴露到公网（HTTPS + 随机域名）：

```bash
# 启动 tunnel
cloudflared tunnel --url http://localhost:38080

# 拿到 URL 后手机浏览器打开，例如：
# https://respiratory-von-carnival-mounted.trycloudflare.com/
```

**安全机制（按端点分级，不要误解）**：

| 端点 | 手机经 tunnel 访问 | 原因 |
|---|---|---|
| `GET /` / `/style.css` / `/app.js` / `/mock` | ✅ 允许 | 纯读，暴露的只是统计数据 |
| **`GET /open?path=...`** | ⚠️ **允许，会在 Mac 本地 `open` 文件** | 仅做白名单路径检查（`is_path_allowed`），**没有**本机直连限制。这是 feature：手机点文件名 → Mac 弹开对应文件。安全依靠 cloudflared 随机 URL + 路径白名单 |
| `POST /archive` / `POST /restore` | ❌ 403 | `is_direct_local()` 检测 `cf-ray / cf-connecting-ip / cf-ipcountry / cdn-loop` header。禁用/启用**只能本机直连**做 |

**结果**：手机能看 dashboard + 能远程打开 Mac 上文件，但**不能禁用 skill**。

### 3.3 CLI 查询

```bash
# 默认最近 30 天 all
~/.claude/hooks/usage-report.sh

# 最近 7 天
~/.claude/hooks/usage-report.sh 7

# 只看某类
~/.claude/hooks/usage-report.sh 30 skill
~/.claude/hooks/usage-report.sh 30 subagent
# 可选类别: skill | clinerule | subagent | explicit | claude | agents | memory | all
```

### 3.4 禁用装饰品

**Dashboard 里（本机）**：每个冷藏项右边有 `[禁用]` 按钮，点 → confirm → 文件移到 `.disabled/` → 按钮变 `[启用]`。

**CLI 批量**：
```bash
# 干跑：看候选列表
~/.claude/hooks/usage-archive-cold.sh --days 30

# 真正禁用（会跳过白名单）
~/.claude/hooks/usage-archive-cold.sh --days 30 --apply

# 列出已禁用
~/.claude/hooks/usage-archive-cold.sh --list

# 恢复单个
~/.claude/hooks/usage-archive-cold.sh --restore <name>
```

**白名单**（在脚本顶部 `WHITELIST` 数组）— 无论冷多久都不禁用：
- `using-superpowers / brainstorming / writing-plans / executing-plans`
- `verification-before-completion / requesting-code-review / receiving-code-review`
- `systematic-debugging / test-driven-development`

---

## 4. 采集的 7 类事件

| 事件类型 | 触发条件 | 是否 pairable |
|---|---|---|
| `skill_read` | Read 工具打开 `*/skills/*/SKILL.md` | ✅ |
| `skill_explicit` | Skill 工具被调用（slash command 走这个） | ❌ |
| `subagent` | Agent / Task 工具派发 subagent | ❌ |
| `clinerule_read` | Read 工具打开 `*/.clinerules/*.md` | ✅ |
| `claude_md_read` | Read 工具打开 `*/CLAUDE.md`（含 global + root + 子项目） | ✅ |
| `agents_md_read` | Read 工具打开 `*/AGENTS.md` | ✅ |
| `memory_read` | Read 工具打开 `*/memory/*.md` | ✅ |

**pairable** = 事件是否参与"配对率"计算（见 5.3）。

**子 agent 内部的 tool 调用也会被捕获**，共享父会话 session_id。

**Bash / Edit / Write 这类工具调用不会被统计** — 系统只关心"Claude 消费了哪些规则/skill/agent"这个维度。

---

## 5. Dashboard 区块说明

按页面从上到下：

### 5.1 Hero（顶部）
- 主标题 + 一句话总结（过去 N 天共触发 X 次，装饰品候选 Y 项）
- **周对比**：近 7 天 vs 前 7 天（绿=上升 / 黄=下降 / 灰=无变化）
- 时间窗 pills：1天 / 7天 / 30天 / 90天 / 1年
- 4 张摘要卡片（时间窗口 / 事件数 / 会话数 / 累计事件数）
- 事件数卡片下有 **sparkline** 显示最近 30 天日触发趋势

### 5.2 Owner 筛选 chips
按"目录归属"筛选 dashboard 里的所有数据。**纯客户端过滤（无刷新）**。
- `全部 / global / builtin / plugin / live_app / live3_app / live4_go_talk / live3_svr_api / live3_svr_admin ...`

**Owner 解析规则**（`compute_owner(path)`）：
- `~/.claude/memory/...` → `live_app`（memory 物理在 ~/.claude 但语义属项目）
- `~/.claude/plugins/...` → `plugin`
- `~/.claude/...` → `global`
- `live_app/<subproject>/...` → 子项目名
- `.clinerules/references/<sub>/...` → `<sub>`
- `live_app/...` 其他 → `live_app`
- Subagent 无路径的（Explore / general-purpose 等）→ `builtin`

### 5.3 跨项目 Today 面板
每个 owner 的最近活动卡片：最近时间 + 事件数 + 最近 5 项事件。解决"我刚才在哪个子项目做什么"。

### 5.4 子项目健康面板
每个已知子项目一张卡片，3 个信号：最近活动 / 事件数 / 最近错误数。
颜色根据最近活动时间：今天=绿 / ≤3天=浅绿 / ≤7天=黄 / >7天=红 / 从未=灰。

### 5.5 已触发区（7 张 active card）
每类事件一张卡片，按次数排序。每行显示：
- 次数 / 名字（可点击 /open 打开文件）/ 会话数 / 配对率 badge（绿/黄/红）/ owner 标签

**配对率（paired_30d）**：
- 定义：一次 read 事件后 5 分钟内，同 session 出现过 `skill_explicit` 或 `subagent` 事件
- 展示：`X/Y 配对` — X 是配对数，Y 是 session != '' 的总事件数
- 意义：区分"读了但没用"和"读了形成工作流"

### 5.6 装饰品候选区（8 个 cold cards）
- 未触发 Skill 读取
- 未触发 Skill 调用
- 未触发 Subagent
- 未触发 .clinerules
- 未触发 CLAUDE.md
- 未触发 memory
- 未触发 AGENTS.md
- 未触发 Plugin 命令

每项显示：名字（可点击）/ 最后触发时间（从未触发 / N 天前）/ owner 标签 / `[禁用]` / `[启用]` 按钮。

**排序**：按"最久未触发"排前面（从未触发 → 最早触发 → 最近触发）。

**已禁用的项**：在列表末尾，行淡化 + `⊘` 前缀 + 按钮变 `[启用]`。

**同名 subagent**：如果 user 和 project 下同名，只显示 project 版本（Claude Code 解析时 project 优先），user 版本隐藏 + 在卡片底部 notice 提示。

### 5.7 CLAUDE.md 热度分析 ⭐️
按 `##` 和 `###` 分节，对每节评分。目的是定位 CLAUDE.md 里可以删减的冷章节。

**每行显示**：
- `[热度 pill]` `[删减收益 pill + 分数]` 章节标题 token 数

**两个信号**：
- **热度**（热/温/冷/纪律）：基于章节引用的资源累计加权触发数
- **删减收益**（高/中/低 + 0-60 分）：`token_score + stale_score - keep_score`

**公式**：
```
token_score: 0(<80) / 10(80-199) / 20(200-399) / 30(≥400)
stale_score: 0(hit≥8) / 10(2-7) / 20(1) / 30(0)
keep_score = 35 * heat_band + 20 * discipline_flag
  heat_band: hot=1.0 / warm=0.5 / cold=0.0
  discipline_flag: 含"禁止/必须/不得/警告/不要/绝不/MUST/NEVER/REQUIRED"
分桶:
  ≥40: 高删减收益 (建议删)
  20-39: 可审查
  <20: 保留
```

**时间加权 hit_count**（A）：
- 近 7 天触发 × 3
- 7-30 天 × 1
- 30+ 天 × 0.3

**Token 估算**：
- 优先使用 `tiktoken cl100k_base`（Claude 的最佳离线近似）
- 未安装时 fallback `bytes / 3.5`
- 按 mtime 缓存，文件没改就不重算

### 5.8 Memory 最近更新
按 mtime 倒序列 Top 10 memory 文件，可点击 /open 在 Mac 打开。hover 文件名用**本地预览** tooltip（`_file_preview` 直读文件前 500 字、跳 frontmatter），不走 LLM `/summary` 端点，避免消耗 AI 摘要配额。

### 5.9 Compact 存档时间轴
按 mtime 倒序列所有 compact-notes 下的 md 文件，可点击打开。hover 文件名同样用本地预览。无统计 sheet。

---

## 6. 核心算法

### 6.1 配对率（paired_30d）

```sql
SELECT name, scope, SUM(paired) / COUNT(*)
FROM (
  SELECT e1.name, e1.scope,
    CASE WHEN EXISTS (
      SELECT 1 FROM events e2
      WHERE e2.session = e1.session
        AND e2.type IN ('skill_explicit', 'subagent')
        AND datetime(e2.ts) BETWEEN datetime(e1.ts) AND datetime(e1.ts, '+5 minutes')
    ) THEN 1 ELSE 0 END AS paired
  FROM events e1
  WHERE e1.type IN (pairable types) AND e1.ts >= cutoff AND e1.session != ''
)
GROUP BY name, scope
```

### 6.2 Session 数
`COUNT(DISTINCT session)` 按 (name, scope) 分组。区分"稳定复用 vs 一次性试验"。

### 6.3 Cold 检测
**不是从 events.db 的缺失推导**，而是**文件系统枚举 minus 事件触发**：
1. 扫 `~/.claude/skills/` 和 `<project>/.claude/skills/` 找所有 SKILL.md
2. 扫 `events.db` 找 30 天内触发过的 `(name, scope)` 集合
3. 差集就是 cold

对 skill 特别：按 `(name, scope)` 联合去重（避免 user 和 project 同名误判）。

对 subagent：按 name 去重 + 同名时 project 优先（Claude Code 解析行为一致）。

---

## 7. Hook 配置

`~/.claude/settings.json` 的 `hooks` 字段：

```json
{
  "hooks": {
    "SessionStart": [{"hooks": [{"command": "bash ~/.claude/hooks/session-start.sh"}]}],
    "PostToolUse": [{"hooks": [{"command": "bash ~/.claude/hooks/usage-tracker.sh"}]}],
    "PreCompact": [...],
    "PostCompact": [...]
  }
}
```

`usage-tracker.sh` 在每次工具调用后被触发，通过 stdin 接收 JSON：
```json
{
  "tool_name": "Read",
  "tool_input": {"file_path": "..."},
  "session_id": "..."
}
```

---

## 8. 禁用机制

**核心原理**：不是改 Claude Code 配置，而是**移动文件位置**。

### 支持的对象类型

| 对象 | 禁用路径 | 恢复路径 |
|---|---|---|
| **Skill** | `mv skills/<name>/ skills/.disabled/<name>/`（整个目录） | 反向 mv |
| **Subagent** | `mv agents/<name>.md agents/.disabled/<name>.md`（单文件） | 反向 mv |
| **scope** 分 user 和 project | `~/.claude/` 下 vs `live_app/.claude/` 下 | 按 scope 路由 |

**不支持禁用**：CLAUDE.md / .clinerules / memory / plugin 命令 — 这些是你手动管理的，dashboard 只做统计不做移动。

### 为什么这个机制安全
- **可逆**：没有删除文件，只是换位置
- **原子**：`os.rename` 是原子操作
- **幂等**：已禁用的再点禁用 → 目标路径存在 → 返回错误不动
- **审计**：每次操作写 `archive-log.jsonl`
- **Claude Code 扫描逻辑**：启动时扫 `skills/*/SKILL.md` 和 `agents/*.md`，**不扫隐藏目录 `.disabled/`**，等同"不存在"

### 端点入口
- **Web UI**：每个冷藏项右侧的 `[禁用]` / `[启用]` 按钮 → POST `/archive` / `/restore`
- **CLI**：`usage-archive-cold.sh` — 批量 + whitelist + dry-run

---

## 9. 重启 / 部署

### 9.1 重启 dashboard
```bash
pkill -f usage-web.py
nohup python3 ~/.claude/hooks/usage-web.py > /tmp/usage-web.log 2>&1 &
```

### 9.2 重启 cloudflared tunnel（URL 会变）
```bash
pkill -f cloudflared
nohup cloudflared tunnel --url http://localhost:38080 > /tmp/cloudflared.log 2>&1 &
# 等 10 秒, 从日志拿新 URL
grep 'trycloudflare.com' /tmp/cloudflared.log
```

### 9.3 开机自启
`~/.zshrc` 已配置 `pgrep -f usage-web.py || nohup python3 ~/.claude/hooks/usage-web.py &` — 开终端时自动拉起。
Cloudflared 没配置自启，需要手动开。

---

## 10. 已知限制

### 10.1 CLAUDE.md 热度分析的盲区
- **资源匹配只靠名字字面量**：章节说"使用 proto 同步流程"但没提具体 skill 名 → 算法匹配不到 → 误判为冷
- **跨章节引用看不到**：A 章节说"见 B 章节"，A 自己没引用 skill 会被误判
- **Token 估算 ±5-10%**：tiktoken 不是 Claude 真正的 tokenizer，但已经是离线最佳近似
- **数据稀疏期**：events.db 积累 < 2 周时，时间加权效果有限，很多章节被误判为冷
- **"纪律性章节"靠关键词保护**：`禁止/必须/不得` 才触发，英文 `MUST/NEVER` 也识别，但语气温和的规则（如"建议"）不受保护
- **短名字（< 4 字符）跳过匹配**：避免 `go`, `pk` 之类误匹配

### 10.2 子 agent 事件的 owner 归类
- Claude Code 内建 subagent（`Explore`, `general-purpose`, `Plan`, `statusline-setup`, `claude-code-guide`）没有对应的 .md 文件 → owner 标为 `builtin`
- Plugin 命令（`codex:setup` 等）owner 标为 `plugin`

### 10.3 数据层
- events.db 无保留策略（永久累积）
- 没有周级 / 月级归档
- 长期运行后可能 > 100MB，目前远低于此

### 10.4 事件采集范围
- 只捕获 `Read / Agent / Task / Skill` 4 类工具调用
- **不记录** Bash / Edit / Write / WebFetch / WebSearch 等其他工具
- 不记录失败的工具调用（目前算成功）

### 10.5 Owner 的硬编码
- `SUBPROJECT_MAP` 硬编码了 live_app 已知子项目
- 新增子项目需要改代码
- `LIVE_APP_PATH` / `LIVE_APP_MEMORY_PATH` 支持 env override

---

## 11. TODO / 延后项

所有讨论过但还没做的东西，按类别和状态分：

### 🟡 等数据积累后再评估

| 项目 | 等什么 | 备注 |
|---|---|---|
| **自适应阈值（B）** | 数据 ≥ 2 周 | 当前硬阈值 50/1/0 够用 |
| **recent_edit_flag** | 数据 ≥ 2 周 + 改造 `analyze_claude_md` 读 git mtime | prune_score 附加信号 |
| **异常峰值标注** | sparkline 有多天数据后 | 标记日序列里的高点 |
| **查询结果缓存** | SQLite 慢之前不做 | 当前响应 < 50ms 够快 |
| **轻量数据保养**（DB 大小等） | DB > 50MB 再做 | |
| **周/月对比更丰富** | 数据多了再细化 | 现在只有"近 7d vs 前 7d" |

### 🟠 有条件再做的维护债

| 项目 | 触发条件 | 备注 |
|---|---|---|
| ~~`usage-web.py` 结构化~~ | ~~文件 > 1200 行~~ | ✅ **v8 已完成**: 拆为 5 个模组 (core/queries/render/main/summary)，最大单档 1192 行 (render), 全部 ≤1200 行。依赖线性 `core → queries → render → main`, `summary` 独立. 每个模组 concern 清晰. |

### 🟢 锦上添花（Codex 建议但未做）

| 项目 | 为什么延后 |
|---|---|
| **cross_ref_in_flag** | 解析 `见 ##X` 脆弱，ROI 低 |
| **abstract_flag** | 启发式容易不准 |
| **CSV/JSON 视图导出** | 没有明确使用场景 |
| **Search box 过滤 cold 列表** | 冷列表目前长度可接受 |
| **已禁用项独立展示区** | 现已在 cold 列表内显示 |

### ❌ 明确不做（Codex 分析过的陷阱）

| 项目 | 不做原因 |
|---|---|
| **Session 管理** | 会和 Claude Code 官方行为打架，变成"脆弱的半个客户端" |
| **Memory / Skill 网页编辑器** | 写操作引入并发覆盖 / 格式约束 / 误改生产上下文 |
| **Build / test 一键按钮** | 执行长任务 + 流式日志 + 失败恢复 + 权限边界快速膨胀 |
| **一键 proto 同步** | 之前做了 `proto-sync-log.sh` 后发现价值低，已删。真正有用是"检测 proto drift"，不是"执行" |
| **Session drill-down** | 容易扩散成 session replay / 事件 timeline / 全文检索，边界失控 |
| **Co-occurrence 洞察** | 数据量小时只产出**伪洞察** |
| **导出清理清单** | 规则不稳时误导"少触发"为"该删除"，可能伤真实资产 |
| **记录 Bash / Edit 事件** | 典型 mission creep，立刻拉高采集/存储/隐私/解释成本 |
| **测试套件 / Docker / 多用户** | 过度工程，personal tool 不需要 |
| **LLM 评分 CLAUDE.md 章节** | 最大陷阱：不可验证 + 会漂移。Codex 明确警告 |
| **D 多信号综合评分** | 权重调参地狱，解释性差 |
| **E 跨章节引用图** | 解析脆弱，ROI 低 |
| **宽限期 / Mark as reviewed** | 用户决定"人工判断就行" |

### 🔵 未来计划：开源成 Claude Code 插件（方案 C）

目标：放到 GitHub 开源，既能通过 `/plugin install` 一键装，又能通过独立 `install.sh` 装可选扩展依赖。

**为什么是方案 C（混合路线）**
- 纯 plugin 安装器不跑自定义脚本，装不了 bun / tiktoken / cloudflared
- 纯独立仓库失去 Claude Code 原生识别 skills/hooks 的能力
- C 方案既被 Claude Code 识别，又有自由安装流程，是 superpowers 等项目走的路

**目录结构**
```
claude-usage-stats/
├── .claude-plugin/plugin.json      # 被 Claude Code 识别
├── hooks/hooks.json                # PostToolUse 注册
├── scripts/                        # 所有 usage-*.sh / .py / .css / .js
├── bin/usage-stats                 # CLI 入口，加入 PATH
├── commands/usage-stats.md         # /usage-stats slash command
├── install.sh                      # 可选：装 tiktoken / cloudflared
└── README.md
```

**关键改造点**
1. 路径变量：`~/.claude/hooks/` → `${CLAUDE_PLUGIN_ROOT}/scripts/`；`~/.claude/usage-stats/` → `${CLAUDE_PLUGIN_DATA}/`（跨插件更新保留数据）
2. 删 live_app 硬编码：`PROJECT_ROOT` / `SUBPROJECT_MAP` / MEMORY_DIR slug 三处。未填 workspace 就只统计 global，owner 降级为 `global/builtin/plugin`
3. 跨平台：`open` 包一层 macOS/Linux/Windows；BSD `date -v-Nd` 换 Python `datetime`
4. Web server 生命周期：不常驻。`/usage-stats` slash command 或 `bin/usage-stats` 启动，Ctrl+C 结束。**不要**塞 SessionStart hook（端口冲突）
5. cloudflare tunnel：移出核心，README 写"可选远程访问"章节
6. tiktoken："有就用，无则 fallback bytes/3.5"，install.sh 可选装
7. 禁用/恢复功能：涉及移动用户 `~/.claude/skills/` 文件，README 强调可逆 + archive-log

**前端演进路径**
- v0.1：Python 拼 HTML，先占坑发出去
- v0.2（可选）：前后端分离，React + Tailwind + 可变字体 bundle 进 `dist/`，Python 只做 JSON API。install.sh 可检测 bun 并走 dev 模式

**需要先决定的事**
- 插件名（`claude-usage-stats`?）
- README 语言（中/英/双语）
- 是否默认启用禁用/恢复功能

**不要做的事**
- 不要在 plugin.json 声明 pip/npm 依赖（插件系统不支持）
- 不要把 cloudflared 二进制塞进仓库（体积 + 许可证问题）
- 不要一上来就前后端一起重构（先发 v0.1）

### 🔴 已知 Bug（低影响）

- **热度阈值偏紧**：`Figma 查询硬规则（强制）` 等含纪律关键词但 token 大的章节仍被标 `高删减收益`，需要 discipline_flag 权重更高（当前 20，可考虑 30+）
- **数据稀疏期误判**：tracker 启动前的触发不在库里，所以短期看所有章节都像 cold
- **第一步先读 / 技术架构概览 等引导性章节**：因为它们是"介绍"不是"引用具体 skill"，容易被误标高删减收益。处理方式是**人工过一遍**，不盲信算法
- **tab 内部内容高度随筛选/展开变动**：骨架本身已稳定（page-header + tab-bar 永不变），但 tab 内部点 owner chip 筛选或点"还有 N 项"展开，会改变 tab-content 高度。这是内容变化不是骨架抖动，可接受。（Codex 方案 C 审查 Q1）

---

## 12. 常见问题

### Q: dashboard 没数据？
1. 确认 `usage-tracker.sh` hook 挂对了（`~/.claude/settings.json` 的 `PostToolUse`）
2. 跑一次 Read/Agent 工具触发 hook
3. 查 `~/.claude/usage-stats/events.db` 是否有行

### Q: 手机点禁用按钮失败？
这是**设计如此**。安全机制拒绝通过 tunnel 的写操作。禁用要回 Mac 本机 `http://localhost:38080` 做。

### Q: cloudflared URL 变了？
临时 tunnel 每次重启都换 URL。要持久 URL 需要 cloudflared 登录账号 + 注册域名。对个人使用来说，每次记一下临时 URL 就行。

### Q: 如何增加一个新的子项目（比如 live5_go_talk）？
改 `usage-web.py` 的 `SUBPROJECT_MAP` 字典，加一行：
```python
"services/live5_go_talk": "live5_go_talk",
```
然后 `usage-web.css` 可以加对应的 `.owner-tag.live5_go_talk` 颜色（可选）。

### Q: 如何增加一个新的事件类型？

改动面比看起来大，完整步骤：

**采集层**（`usage-tracker.sh`）
1. 加对应 Read/Agent/Skill case 分支 + emit 调用
2. 确认 schema 够用（events 表有 ts/type/name/scope/path/description/session）

**事件 schema**（`usage-web.py`）
3. 顶部 `EVENT_TYPES` 数组加 `(type, label, pairable)` 一行
4. `CATEGORIES` 和 `PAIRABLE_READ_TYPES` 是从 `EVENT_TYPES` 派生的，不用手动加

**Active section 渲染**
5. 如果新事件有独立 path → `compute_owner()` 应该能处理（否则加 owner 推导）
6. 如果是显式调用类（无 path）→ 加 `resolve_xxx_path()` helper
7. 检查 `attach_owner_active()` 需不需要加新分支

**Cold detection**（如果需要）
8. 加 `list_xxx_files()` 函数枚举文件系统
9. 在 `render()` 里加 cold data 计算
10. 加 `render_risk("cold_xxx", ...)` 调用
11. `LABELS` 字典加 `cold_xxx` 文案
12. 加 `query_last_seen(conn, "xxx_type")` + `ls_xxx` 变量
13. `sort_cold_items()` 调用

**CLI 报告**（`usage-report.sh`）
14. `section()` 支持新 type
15. `case "$KIND"` 加对应选项

**重启**
16. `pkill -f usage-web.py; ...` 重启 dashboard
17. `events.db` 不用改，新 type 可以直接写入

**快速检查**：改完搜索 `grep -n '<新 type>' ~/.claude/hooks/usage-*.{py,sh,css}` 确认覆盖所有地方。

### Q: tiktoken 没装怎么办？
系统会自动 fallback 到 `bytes / 3.5`（精度下降）。装：
```bash
pip install --break-system-packages --user tiktoken
```

### Q: 如何彻底关掉这个系统？
1. `pkill -f usage-web.py` 关 dashboard
2. `pkill -f cloudflared` 关 tunnel
3. 删除 `~/.claude/settings.json` 里的 `PostToolUse` hook 块
4. 可选：`rm -rf ~/.claude/usage-stats/` 删数据

---

## 13. 设计原则（给未来 session）

如果未来要扩展这个系统，Codex 多轮审计得出的核心原则：

1. **读 > 写**：避免并发和覆盖问题
2. **状态面板 > 一键执行**：执行入口风险大
3. **信号 > 日志**：异常比通用日志有行动价值
4. **上下文恢复 > 控制面板**：工作台核心是快速进入正确位置，不是操控一切
5. **先采集后展示**：改 schema 前先观察数据
6. **运行时 zero-deps，分析层允许单依赖**：HTTP server / tracker / render 全部 Python stdlib + vanilla JS/CSS 零依赖；**tiktoken 是分析层的可选依赖**（缺失时 fallback 到 `bytes/3.5`，不会崩）。不要再加第二个外部依赖
7. **不做成分析平台**：识别装饰品 + 省 token 是唯一目的，不扩散成通用监控

---

## 14. 架构总览

```
┌─────────────────────────────────────┐
│  Claude Code session                │
│    ↓ 每次工具调用                    │
│  PostToolUse hook                    │
│    ↓                                 │
│  usage-tracker.sh                    │
│    ├─→ events.jsonl (纯备份)         │
│    └─→ events.db (真理源)            │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│  usage-web.py                        │
│    ├─ GET / → HTML dashboard         │
│    ├─ GET /style.css                 │
│    ├─ GET /app.js                    │
│    ├─ GET /open?path=... → os.open   │
│    ├─ POST /archive → mv to .disabled/│
│    └─ POST /restore → mv back        │
└─────────────────────────────────────┘
         ↓                    ↓
  localhost:38080    cloudflared tunnel
  (本机可读+可写)    (手机可读+可触发 /open, 不能 POST 写)

┌─────────────────────────────────────┐
│  CLI 工具（按需跑）                  │
│    ├─ usage-report.sh  查询排行      │
│    ├─ usage-archive-cold.sh 批量禁用 │
│    └─ usage-rebuild-db.sh 灾备重建   │
└─────────────────────────────────────┘
```

---

## 15. 版本历史摘要

- **v1**：简陋的 shell 脚本，用 jq 统计 jsonl
- **v2**：加 SQLite + Web dashboard + CSS 样式
- **v3**：重构 bug 修复 + 中文化 + 暗色 UI + owner 标签
- **v4**：Codex 多轮审查 + 精度 bug 修复
- **v5**：禁用工具 + 跨项目面板 + CLAUDE.md 热度分析
- **v6**：prune_score + tiktoken 精确 token + 对齐优化
- **v7**：4 tab 导航 + 方案 C 前端重构
- **v8**（当前）：Card flip + AI 摘要 + 模组拆分 + Cyberpunk 主题
  - **Card flip**：所有 7 类卡片整体可点翻面, 3D Y-rotate 420ms, grid `face` 自动取 max-height, Memory 改 sheet 抽屉；背面内容覆盖 Hero/Today/Health/Active/Cold/CLAUDE.md
  - **AI 摘要系统**：hover 文件名显示 Claude 生成的 10-15 字中文摘要. 后端 `/summary` 调 `claude -p` 子进程（借用订阅制 auth，不用 API key），两层缓存（JS session + disk JSON）, 同 path 并发 dedup, 日配额 100 次可配, in-flight ≤8, 失败退款
  - **全局 tooltip 系统**：JS 创建单一 `#global-tooltip` 挂 body, `data-tip`/`data-summary` 属性触发, 逃离任何 overflow 容器, hover delay 400ms 避免误触 fetch
  - **Neo-Terminal cyberpunk 主题**：`#39ff14` 荧光绿 + Chakra Petch/JetBrains Mono + 双色霓虹暈 + CRT 掃描線
  - **模组拆分**：`usage-web.py` 3116 行 → 5 个 Python 模组（core 622 + queries 773 + render 1192 + summary 222 + main 411），最大单档 1192，全部 ≤1200 行阈值
  - **ThreadingHTTPServer**：替代单线程 HTTPServer, 避免 `claude -p` 60s 子进程阻塞
  - **新端点**：`/summary`, `/summary-status`, `/prune-list`, `/clear-summary-cache`
  - **prune dot 点击筛选**：CLAUDE.md 卡片内点 高/中/低 dot 按 bucket 筛选 section, 再点取消
  - **Operator Console 方案 A（未实施）**: 开源成 Claude Code 插件的方案 C 已有详细计划, 见 🔵 未来计划
  - 稳定骨架（page-header + sticky tab-bar 永不变动）+ 自包含 tab，修复 tab 切换上下抖动
  - 设计 token 体系：6 档 spacing / 3 档 radius / 6 组 typography
  - 卡片材质统一升级（linear-gradient bg + 多层 shadow + hairline top highlight）
  - 微动画收敛（150-300ms + `cubic-bezier(.2,.8,.2,1)`，删除 pulseGlow）
  - Codex 审查 round 2 修复：tab `pushState` 历史（Q10）、`.page` grid 1fr 替代硬编码高度计算（Q2）、移除死 `data-tab` body 属性（Q8）、spacing token 纪律（Q7）
  - Mobile 兼容：`100dvh`、`overflow-x:hidden`、tab 小屏收缩、`.row .num` 桌面 18px / 手机 15px
  - 时间 pills 点击保留当前 tab hash（不再跳回总览）
  - 开源成 Claude Code 插件的方案 C 计划写入 §11 🔵（未实施）

---

_最后更新：2026-04-14 (v8)_
_维护位置：`~/.claude/hooks/USAGE-STATS.md`_
