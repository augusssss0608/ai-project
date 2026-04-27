#!/usr/bin/env python3
"""直接调 Telegram Bot API 发消息, 不依赖 MCP plugin.

用途: /loop 任务给 Telegram 发通知时避免 MCP 长期挂起失败的问题.
读 token 从 ~/.claude/channels/telegram/.env (同 MCP plugin 共用配置).
读 chat_id 从 ~/.claude/channels/telegram/access.json 的 allowFrom[0].

用法:
    python3 tg_notify.py "消息内容"
    python3 tg_notify.py --stdin   # 从 stdin 读消息 (支持多行)

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
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            for key in TOKEN_KEYS:
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("token key not found in telegram .env")


def read_chat_id() -> str:
    with open(ACCESS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    ids = data.get("allowFrom", [])
    if not ids:
        raise RuntimeError("no allowFrom chat_id in access.json")
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


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: tg_notify.py <text>    or    tg_notify.py --stdin", file=sys.stderr)
        return 1
    if sys.argv[1] == "--stdin":
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
