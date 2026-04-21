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
    """按 ts desc 返回该源最近 limit 条正例."""
    out = []
    for url, v in feedback.get("votes", {}).items():
        if (v or {}).get("source") != source_id:
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
    """现场生成 examples.md 内容 (不落盘), 直接嵌入 scorer prompt."""
    positives = get_positives(source_id, feedback, limit=pos_limit)
    negatives = _history.get_negatives(source_id, feedback, days=7, limit=neg_limit)

    lines = ["# 正例 (用户标记有帮助)"]
    if positives:
        for p in positives:
            date = (p.get("ts") or "")[:10]
            lines.append(f"- [{date}] {p.get('title', '')} — {p.get('url', '')}")
    else:
        lines.append("- (暂无)")

    lines.append("")
    lines.append("# 负例 (展示过但未点赞, >= 7 天)")
    if negatives:
        for n in negatives:
            date = (n.get("first_ts") or "")[:10]
            title = n.get("title", "")
            url = n.get("url", "")
            lines.append(f"- [{date}] {title} — {url} (曝光 {n.get('count', 1)} 次)")
    else:
        lines.append("- (暂无)")
    return "\n".join(lines)
