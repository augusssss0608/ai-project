#!/usr/bin/env python3
"""AI 大事抓取层 debug 入口 (v2).

只跑 fetchers + filters, 不跑 scorer / summary / analysis.
输出每源原始抓取结果到 /tmp/ai-news-raw-{source_id}.json, 供调 fetcher.yaml 参数时看.

Pipeline 完整流程由 /loop 主 agent 通过 ai-news-fetch skill 驱动, 不走这个脚本.
"""
import json
import os
import sys
import yaml
from pathlib import Path

# hooks/ 根 (parent of ai_news/) 加进 sys.path
_HOOKS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HOOKS_ROOT not in sys.path:
    sys.path.insert(0, _HOOKS_ROOT)
from ai_news.data.fetchers import fetch_one
from ai_news.data.filters import apply_hard_filter

SOURCES_DIR = Path.home() / "Desktop" / "ai-project" / ".claude" / "skills" / "ai-news-filter" / "sources"
OUT_TPL = "/tmp/ai-news-raw-{}.json"

SOURCE_IDS = ["hackernews", "github_trending"]


def load_fetcher_yaml(source_id: str) -> dict:
    path = SOURCES_DIR / source_id / "fetcher.yaml"
    if not path.is_file():
        return {"type": "", "params": {}}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main():
    for sid in SOURCE_IDS:
        cfg = load_fetcher_yaml(sid)
        res = fetch_one(sid, cfg)
        if res.get("items"):
            filtered = apply_hard_filter(res["items"])
            res["items_before_hard_filter"] = len(res["items"])
            res["items"] = filtered
        out_path = OUT_TPL.format(sid)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        print(f"[{sid}] {len(res.get('items', []))} items -> {out_path} "
              f"(err: {res.get('error') or '-'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
