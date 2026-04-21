"""evolve 辅助: 备份 source.md.v{N} + 写 diff log.
实际的 AI 重写工作由 evolve-source-preferences subagent 做, 这里只管工程层面."""
import json
import os
import shutil
from datetime import datetime, timezone

EVOLVE_LOG_PATH = os.path.expanduser("~/Desktop/ai-project/data/ai-news-evolve-log.jsonl")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_frontmatter(source_md_path: str) -> dict:
    """解析 source.md 的 YAML frontmatter (--- ... ---). 返回 dict, 失败返回空."""
    if not os.path.isfile(source_md_path):
        return {}
    out = {}
    with open(source_md_path, "r", encoding="utf-8") as f:
        content = f.read()
    if not content.startswith("---"):
        return {}
    try:
        end = content.index("\n---", 3)
        fm_text = content[3:end]
    except ValueError:
        return {}
    for line in fm_text.strip().splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip().strip('"\'')
        if v.isdigit():
            out[k] = int(v)
        elif v.lower() in ("true", "false"):
            out[k] = v.lower() == "true"
        else:
            out[k] = v
    return out


def backup_source(source_md_path: str, evolve_count: int) -> str:
    """cp source.md → source.md.v{evolve_count}. 返回备份路径."""
    backup = f"{source_md_path}.v{evolve_count}"
    shutil.copy2(source_md_path, backup)
    return backup


def write_evolve_log(entry: dict):
    """追加一行 jsonl log. entry 至少含 source / from / to."""
    os.makedirs(os.path.dirname(EVOLVE_LOG_PATH), exist_ok=True)
    entry.setdefault("ts", _now_iso())
    with open(EVOLVE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
