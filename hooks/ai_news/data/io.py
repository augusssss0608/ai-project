"""读写 ai-news.json (原子 rename) + source.md / examples.md IO helpers."""
import json
import os
from typing import Optional

AI_NEWS_PATH = os.path.expanduser("~/Desktop/ai-project/data/ai-news.json")


def read_ai_news() -> Optional[dict]:
    if not os.path.isfile(AI_NEWS_PATH):
        return None
    try:
        with open(AI_NEWS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def write_ai_news_atomic(payload: dict):
    os.makedirs(os.path.dirname(AI_NEWS_PATH), exist_ok=True)
    tmp = AI_NEWS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, AI_NEWS_PATH)


def read_source_md(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_source_md_atomic(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)
