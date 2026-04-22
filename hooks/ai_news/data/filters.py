import re

CORE_AI_RE = re.compile(
    r"(Claude|Anthropic|ChatGPT|OpenAI|GPT-|Sora|Gemini|Bard|DeepSeek|Qwen|"
    r"LLaMA|Llama|Mistral|Grok|Copilot|Cursor|Perplexity|Midjourney|Firefly|"
    r"Stable\s*Diffusion|Hugging\s*Face|Kimi|Doubao|豆包|文心|通義|通义|"
    r"智譜|智谱|GLM|Minimax|百川|"
    r"Opus|Sonnet|Haiku)",
    re.I,
)

AI_PRODUCT_RE = re.compile(
    r"(" + CORE_AI_RE.pattern.strip("()") + r"|"
    r"o1\b|o3\b|o4\b|o5\b|Yi\b|MCP|agent|agentic|"
    r"大(?:型|语|語)言模型|大模型|生成式|人工智慧|人工智能|LLM)",
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
    if HARD_NOISE_RE.search(title):
        return False
    if CORE_AI_RE.search(title):
        return True
    if AI_PRODUCT_RE.search(title) and not NOISE_RE.search(title):
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
