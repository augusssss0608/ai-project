"""反馈读写 + 启动阶段判定 + few-shot 正负例构造."""
import json
import os

FEEDBACK_PATH = os.path.expanduser("~/Desktop/ai-project/data/ai-news-feedback.json")


def load_feedback() -> dict:
    """读 ai-news-feedback.json. 失败返回空 {'votes': {}}."""
    if not os.path.isfile(FEEDBACK_PATH):
        return {"votes": {}}
    try:
        with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"votes": {}}
        data.setdefault("votes", {})
        return data
    except Exception:
        return {"votes": {}}


def get_stage(source_id: str, feedback: dict) -> str:
    """按源独立判定阶段. 空 source 视为未知, 不计入任何源."""
    count = 0
    for v in feedback.get("votes", {}).values():
        vs = (v or {}).get("source", "")
        if vs == source_id:
            count += 1
    if count < 10:
        return "cold"
    if count < 50:
        return "mid"
    return "hot"


def get_positives(source_id: str, feedback: dict, limit: int = 10) -> list:
    """返回该源正例 (score=up 或 star). star 优先排在前, 内部按 ts desc."""
    stars, ups = [], []
    for url, v in feedback.get("votes", {}).items():
        if v.get("source") != source_id:
            continue
        score = v.get("score")
        if score not in ("up", "star"):
            continue
        entry = {
            "url": url,
            "title": v.get("title", ""),
            "ts": v.get("ts", ""),
            "score": score,
        }
        (stars if score == "star" else ups).append(entry)
    stars.sort(key=lambda x: x["ts"], reverse=True)
    ups.sort(key=lambda x: x["ts"], reverse=True)
    return (stars + ups)[:limit]


def get_explicit_negatives(source_id: str, feedback: dict, limit: int = 10) -> list:
    """返回该源显式负例 (score=down). ts desc."""
    out = []
    for url, v in feedback.get("votes", {}).items():
        if v.get("source") != source_id:
            continue
        if v.get("score") != "down":
            continue
        out.append({
            "url": url,
            "title": v.get("title", ""),
            "ts": v.get("ts", ""),
        })
    out.sort(key=lambda x: x["ts"], reverse=True)
    return out[:limit]


from ai_news import history as _history


def build_examples_inline(source_id: str, feedback: dict,
                          pos_limit: int = 10, neg_limit: int = 10) -> str:
    """现场生成 examples.md 内容 (不落盘), 直接嵌入 scorer prompt.

    四组信号 (强度从高到低):
    - 强正例 ⭐ star: 用户明确标记超赞, scorer 对同类主题打分应最高
    - 正例 👍 up: 用户标记有用
    - 显式负例 👎 down: 用户明确不感兴趣, 强信号避开同类
    - 隐式负例 (history): 曝光 >=7 天无任何反馈, 弱信号
    """
    positives = get_positives(source_id, feedback, limit=pos_limit)
    stars = [p for p in positives if p.get("score") == "star"]
    ups = [p for p in positives if p.get("score") == "up"]
    neg_explicit = get_explicit_negatives(source_id, feedback, limit=neg_limit)
    neg_implicit = _history.get_negatives(source_id, feedback, days=7, limit=neg_limit)

    lines = []

    lines.append("# 强正例 ⭐ (用户标记超赞, 权重最高)")
    if stars:
        for p in stars:
            date = (p.get("ts") or "")[:10]
            lines.append(f"- [{date}] {p.get('title', '')} — {p.get('url', '')}")
    else:
        lines.append("- (暂无)")

    lines.append("")
    lines.append("# 正例 👍 (用户标记有用)")
    if ups:
        for p in ups:
            date = (p.get("ts") or "")[:10]
            lines.append(f"- [{date}] {p.get('title', '')} — {p.get('url', '')}")
    else:
        lines.append("- (暂无)")

    lines.append("")
    lines.append("# 显式负例 👎 (用户明确不感兴趣, 强信号需避开同类主题)")
    if neg_explicit:
        for n in neg_explicit:
            date = (n.get("ts") or "")[:10]
            lines.append(f"- [{date}] {n.get('title', '')} — {n.get('url', '')}")
    else:
        lines.append("- (暂无)")

    lines.append("")
    lines.append("# 隐式负例 (曝光 >= 7 天从未点任何反馈, 弱信号)")
    if neg_implicit:
        for n in neg_implicit:
            date = (n.get("first_ts") or "")[:10]
            title = n.get("title", "")
            url = n.get("url", "")
            lines.append(f"- [{date}] {title} — {url} (曝光 {n.get('count', 1)} 次)")
    else:
        lines.append("- (暂无)")
    return "\n".join(lines)
