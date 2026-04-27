import re

CORE_AI_RE = re.compile(
    r"(Claude|Anthropic|ChatGPT|OpenAI|GPT|Sora|Gemini|Bard|DeepSeek|Qwen|"
    r"LLaMA|Llama|Mistral|Grok|Copilot|Cursor|Perplexity|Midjourney|Firefly|"
    r"Stable\s*Diffusion|Hugging\s*Face|Kimi|Doubao|豆包|文心|通義|通义|"
    r"智譜|智谱|GLM|Minimax|百川|讯飞|星火|"
    r"Opus|Sonnet|Haiku)",
    re.I,
)

AI_PRODUCT_RE = re.compile(
    r"(" + CORE_AI_RE.pattern.strip("()") + r"|"
    r"o1\b|o3\b|o4\b|o5\b|Yi\b|MCP|agent|agentic|智能体|"
    r"大(?:型|语|語)言模型|大模型|生成式|人工智慧|人工智能|LLM|\bAI\b)",
    re.I,
)

_NOISE_TERMS = [
    "融資", "融资", "併購", "并购", "IPO", "收購", "收购", "股價", "股价",
    "估值", "投資人", "投资人", "私募", "募資", "募资", "季報", "季报",
    "財報", "财报", "營收", "营收", "業績", "业绩", "淨利", "净利",
    "工廠", "工厂", "產業鏈", "产业链", "供應鏈", "供应链", "晶圓", "晶圆",
    "代工", "製造業", "制造业", "產業界", "产业界",
    "汽車", "汽车", "電動車", "电动车", "自動駕駛", "自动驾驶", "造車", "造车",
    "車企", "车企", "NOA", "自駕", "自驾", "智駕", "智驾", "充電樁", "充电桩",
    "ESG", "淨零", "净零", "永續", "永续", "減碳", "减碳", "碳排",
    "資安", "资安", "漏洞", "駭客", "骇客", "攻擊", "攻击", "惡意", "恶意",
    "malware", "ransomware", "CVE", "NKAbuse", "詐騙", "诈骗", "釣魚", "钓鱼",
    "FIDO", "KYA", "KYC", "GDPR", "合規", "合规", "審計", "审计",
    "制裁", "禁令", "關稅", "关税", "貿易戰", "贸易战", "出口管制",
    "醫療", "医疗", "診斷", "诊断", "臨床", "临床",
    "週報", "周报", "回顧", "回顾",
]
NOISE_RE = re.compile("|".join(re.escape(t) for t in _NOISE_TERMS), re.I)

_HARD_NOISE_TERMS = [
    "漏洞", "駭客", "骇客", "攻擊", "攻击", "惡意", "恶意", "malware",
    "ransomware", "詐騙", "诈骗", "CVE", "NKAbuse", "零時差", "零日",
    "併購", "并购", "融資", "融资", "IPO", "收購", "收购", "股價", "股价",
    "關稅", "关税", "制裁",
]
HARD_NOISE_RE = re.compile("|".join(re.escape(t) for t in _HARD_NOISE_TERMS), re.I)


def is_pure_ai_news(title: str, desc: str = "") -> bool:
    text = f"{title}\n{desc}"
    if HARD_NOISE_RE.search(text):
        return False
    if CORE_AI_RE.search(text):
        return True
    if AI_PRODUCT_RE.search(text) and not NOISE_RE.search(text):
        return True
    return False


def apply_hard_filter(items: list) -> list:
    out = []
    for it in items:
        title = it.get("title", "")
        desc = it.get("desc", "")
        if is_pure_ai_news(title, desc):
            out.append(it)
    return out


def apply_dedup_filter(items: list, known_urls: set) -> list:
    """URL 全量去重. 曾在 history.jsonl 出现过的 URL 一律剔除.

    覆盖两类场景:
    - 用户明确 down 过 (投票前必然展示过, URL 已在 history)
    - 用户看到过但没点反馈 (已在 history)
    """
    return [it for it in items if it.get("url", "") not in known_urls]


CLAUDE_SPECIFIC_RE = re.compile(
    r"("
    r"Claude|Anthropic|"
    r"MCP\b|Model\s*Context\s*Protocol|"
    r"claude[-_\s]?code|claude[-_\s]?desktop|"
    r"agent[-_\s]?skills?|skills?\s+for\s+Claude"
    r")",
    re.I,
)


def apply_claude_only_filter(items: list) -> list:
    """仅用于 github_trending: 只保留明确跟 Claude 生态相关的仓库.
    宽松规则: Claude / Anthropic / MCP / claude-code / agent skills 等都算.
    匹配 title + desc."""
    out = []
    for it in items:
        text = f"{it.get('title', '')}\n{it.get('desc', '')}"
        if CLAUDE_SPECIFIC_RE.search(text):
            out.append(it)
    return out


# threads 专用宽松规则: 接受所有 AI_PRODUCT_RE 匹配, 加上 threads 上常见的 AI 工具/术语.
# HARD_NOISE_RE 仍作为硬噪声拦截 (财报/漏洞/制裁 等)
THREADS_LOOSE_RE = re.compile(
    r"(" + AI_PRODUCT_RE.pattern.strip("()") + r"|"
    r"Codex|Cursor|Windsurf|Cline|Antigravity|Lovable|v0\b|Replit|"
    r"提示詞|提示词|提示工程|prompt[\s_-]*engineering|"
    r"AI\s*(工具|助手|助理|原生|代理|编程|編程)|"
    r"(Vibe|vibe)[\s_-]*(coding|code))",
    re.I,
)


def apply_threads_loose_filter(items: list) -> list:
    """仅用于 threads: 比 apply_hard_filter 宽松, 允许任何 AI 产品/工具提及.
    规则: 命中 THREADS_LOOSE_RE (含 AI_PRODUCT_RE + 常见 AI coding 工具 + prompt 相关), 且不命中 HARD_NOISE_RE."""
    out = []
    for it in items:
        text = f"{it.get('title', '')}\n{it.get('desc', '')}"
        if HARD_NOISE_RE.search(text):
            continue
        if THREADS_LOOSE_RE.search(text):
            out.append(it)
    return out
