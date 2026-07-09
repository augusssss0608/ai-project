#!/usr/bin/env python3
"""直接调 Telegram Bot API 发消息, 不依赖 MCP plugin.

用途: ai-news pipeline 给 Telegram 发通知, 跨 mac 和 cloud routine 都能跑.

token / chat_id 来源 (优先级):
1. env var TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (云端 routine 走这条)
2. fallback 本地文件 (mac 走这条):
   - token 从 ~/.claude/channels/telegram/.env
   - chat_id 从 ~/.claude/channels/telegram/access.json 的 allowFrom[0]

用法:
    python3 tg_notify.py "消息内容"
    python3 tg_notify.py --stdin   # 从 stdin 读消息 (支持多行)
    python3 tg_notify.py --daily-report cloud-sync/ai-news.json \
        [--extra "附加告警行"]... [--extra-file <path>]...
        # 从 ai-news.json 程序化生成 §2.7 日报消息并发送.
        # agent 手拼消息会随机漏掉 github_alert 条件行 (2026-07-09 实际漏过),
        # 所以拼装收进脚本; --extra 可重复, 用于附加告警.
        # --extra-file: 文件存在则逐行读为告警行 (空行跳过), 不存在静默跳过——
        # 让 §2.7 的调用命令永远同一条, push 验证失败的告警由 §2.6.1 写文件传递,
        # 不依赖 agent 记得改命令. 本脚本不删该文件 (发送失败重试时告警不能丢).

退出码: 0 成功, 非 0 失败. 脚本不会把 token 写到任何输出.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ENV_PATH = os.path.expanduser("~/.claude/channels/telegram/.env")
ACCESS_PATH = os.path.expanduser("~/.claude/channels/telegram/access.json")


TOKEN_KEYS = ("TELEGRAM_BOT_TOKEN", "BOT_TOKEN", "TOKEN")


def read_token() -> str:
    # 优先 env var (云端 routine 没本地文件)
    env_tok = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if env_tok:
        return env_tok
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            for key in TOKEN_KEYS:
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("token key not found in env var TELEGRAM_BOT_TOKEN or telegram .env")


def read_chat_id() -> str:
    # 优先 env var (云端 routine 没本地文件)
    env_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if env_id:
        return env_id
    with open(ACCESS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    ids = data.get("allowFrom", [])
    if not ids:
        raise RuntimeError("no chat_id in env var TELEGRAM_CHAT_ID or access.json allowFrom")
    return str(ids[0])


def send_message(text: str) -> None:
    token = read_token()
    chat_id = read_chat_id()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        # e.read() 可能含 token-less 错误信息, 但谨慎不输出具体 body
        raise RuntimeError(f"HTTP {e.code}") from None
    except Exception as e:
        raise RuntimeError(f"{type(e).__name__}") from None
    if not result.get("ok"):
        # 错误描述通常不含 token, 但仍做安全截断
        desc = str(result.get("description", ""))[:120]
        raise RuntimeError(f"api: {desc}")


GITHUB_DIMS = ("daily", "weekly", "monthly", "total")


def build_daily_report(json_path: str, extra_lines: list) -> str:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return build_daily_report_from_data(data, extra_lines)


def build_daily_report_from_data(data: dict, extra_lines: list) -> str:
    pm = data.get("pipeline_metrics") or {}
    sources = data.get("sources") or []

    def count(sid: str) -> int:
        by_metrics = (pm.get("sources") or {}).get(sid)
        if by_metrics is not None:
            return by_metrics
        return next((len(s.get("items") or []) for s in sources if s.get("id") == sid), 0)

    total = pm.get("total_items")
    if total is None:
        total = sum(len(s.get("items") or []) for s in sources)
    dedup = pm.get("dedup") or pm.get("dedupe") or {}
    stages = data.get("stage_by_source") or {}
    lines = [
        f"[ai-news] 已刷新 {total} 则 · 去重 {dedup.get('suppressed_total', 0)} 条",
        f"HN {count('hackernews')} · GitHub {count('github_trending')} · Threads {count('threads')}",
        "阶段: HN {} · GitHub {} · Threads {}".format(
            *(stages.get(sid, "?") for sid in ("hackernews", "github_trending", "threads"))
        ),
    ]
    gh = next((s for s in sources if s.get("id") == "github_trending"), {})
    dim_counts = {d: 0 for d in GITHUB_DIMS}
    for it in gh.get("items") or []:
        if it.get("dimension") in dim_counts:
            dim_counts[it["dimension"]] += 1
    zero_dims = [d for d in GITHUB_DIMS if dim_counts[d] == 0]
    if zero_dims:
        lines.append("⚠️ GitHub 维度空: " + " · ".join(zero_dims))
    if gh.get("error"):
        lines.append("⚠️ GitHub 抓取错误: " + str(gh["error"])[:120])
    if gh.get("warning"):
        lines.append("⚠️ GitHub " + str(gh["warning"])[:120])
    lines.extend(extra_lines)
    lines.append("dashboard: http://localhost:38080/#news")
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: tg_notify.py <text> | --stdin | --daily-report <ai-news.json> [--extra <line>]...", file=sys.stderr)
        return 1
    if sys.argv[1] == "--daily-report":
        if len(sys.argv) < 3:
            print("usage: tg_notify.py --daily-report <ai-news.json> "
                  "[--extra <line>]... [--extra-file <path>]...", file=sys.stderr)
            return 1
        extra_lines = []
        rest = sys.argv[3:]
        while rest:
            if rest[0] == "--extra" and len(rest) >= 2:
                extra_lines.append(rest[1])
            elif rest[0] == "--extra-file" and len(rest) >= 2:
                if os.path.exists(rest[1]):
                    with open(rest[1], "r", encoding="utf-8") as f:
                        extra_lines.extend(
                            ln.strip() for ln in f if ln.strip())
            else:
                print(f"unexpected arg: {rest[0]}", file=sys.stderr)
                return 1
            rest = rest[2:]
        try:
            text = build_daily_report(sys.argv[2], extra_lines)
        except Exception as e:
            print(f"build daily report failed: {type(e).__name__}: {e}", file=sys.stderr)
            return 2
    elif sys.argv[1] == "--stdin":
        text = sys.stdin.read()
    else:
        text = sys.argv[1]
    if not text.strip():
        print("empty message", file=sys.stderr)
        return 1
    try:
        send_message(text)
    except Exception as e:
        print(f"tg_notify failed: {e}", file=sys.stderr)
        return 2
    print("sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
