#!/usr/bin/env python3
"""Usage stats web dashboard — thin HTTP 殼.

业务逻辑全部在 usage_web_core / usage_web_queries / usage_web_render 模组.
此文件只保留 Handler 路由 + archive/security + main() 入口.

启动: python3 ~/.claude/hooks/usage-web.py [port]
默认端口 38080. 浏览器打开 http://localhost:38080
"""
import sqlite3
import subprocess
import sys
import os
import html
import time

# Sibling modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_web_summary as summary_mod
from usage_web_core import *
from usage_web_queries import *
from usage_web_render import *
# `import *` 排除底線開頭, 明確 import Handler 需要的私有名
from usage_web_render import _file_link  # may be referenced
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta, timezone



# ============================================================
# 区块: HTTP Handler / 静态资源 / /open 端点
# ============================================================
MOCK_PATH = "/tmp/dash-mock.html"

# /open 端点允许的路径白名单根目录
OPEN_ALLOWED_ROOTS = [
    os.path.realpath(os.path.expanduser("~/.claude")),
    os.path.realpath(PROJECT_ROOT),
    os.path.realpath(MEMORY_DIR),
]


def is_path_allowed(path: str) -> bool:
    """防路径越权: 必须是真实存在的文件，且在白名单根目录下."""
    try:
        real = os.path.realpath(path)
    except Exception:
        return False
    if not os.path.isfile(real):
        return False
    for root in OPEN_ALLOWED_ROOTS:
        if real.startswith(root + os.sep) or real == root:
            return True
    return False


def is_direct_local(headers) -> bool:
    """检测请求是否来自直连 localhost (非 cloudflare tunnel).
    cloudflare tunnel 会添加 cf-ray / cf-connecting-ip 等特征 header."""
    suspicious = ["cf-ray", "cf-connecting-ip", "cf-ipcountry", "cdn-loop"]
    for h in suspicious:
        if headers.get(h):
            return False
    return True


# 禁用工具: archive 的核心逻辑 (web 端复用)
ARCHIVE_LOG_PATH = os.path.expanduser("~/Desktop/ai-project/data/archive-log.jsonl")


# ============================================================
# 区块: 新闻投票 (helpful feedback)
# ============================================================
def load_news_votes() -> dict:
    """读 ai-news-feedback.json, 失败返回空 dict. 返回 {url: entry}."""
    import json
    if not os.path.isfile(NEWS_VOTES_PATH):
        return {}
    try:
        with open(NEWS_VOTES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("votes", {}) if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_news_votes(votes: dict):
    """原子写入: tmp + rename. 保留既有 favorites 不覆盖."""
    import json
    os.makedirs(os.path.dirname(NEWS_VOTES_PATH), exist_ok=True)
    existing = {}
    if os.path.isfile(NEWS_VOTES_PATH):
        try:
            with open(NEWS_VOTES_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f) or {}
        except Exception:
            existing = {}
    payload = {
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "votes": votes,
        "favorites": existing.get("favorites", {}),
    }
    tmp = NEWS_VOTES_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, NEWS_VOTES_PATH)


def _counts_by_score(votes: dict) -> dict:
    """按 score 分桶计数."""
    out = {"down": 0, "up": 0, "star": 0}
    for v in votes.values():
        s = v.get("score")
        if s in out:
            out[s] += 1
    return out


def load_news_favorites() -> dict:
    """读 ai-news-feedback.json 的 favorites 段. 返回 {url: entry}."""
    import json
    if not os.path.isfile(NEWS_VOTES_PATH):
        return {}
    try:
        with open(NEWS_VOTES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("favorites", {}) if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_news_favorites(favs: dict):
    """写回 favorites, 保留既有 votes. 原子 rename."""
    import json
    os.makedirs(os.path.dirname(NEWS_VOTES_PATH), exist_ok=True)
    # 读回来合并, 避免覆盖 votes
    existing = {}
    if os.path.isfile(NEWS_VOTES_PATH):
        try:
            with open(NEWS_VOTES_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f) or {}
        except Exception:
            existing = {}
    payload = {
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "votes": existing.get("votes", {}),
        "favorites": favs,
    }
    tmp = NEWS_VOTES_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, NEWS_VOTES_PATH)
# Summary 相關邏輯已搬到 usage_web_summary.py 模組, 見 import summary_mod as summary
# 向下相容 aliases (減少下面代碼改動)
_get_summary_status = summary_mod.get_status
_clear_summary_cache = summary_mod.clear_cache


# Thin wrapper 指向 summary_mod (舊代碼直接呼叫 get_or_generate_summary 的地方仍能工作)
get_or_generate_summary = summary_mod.get_or_generate


def archive_object(obj_type: str, name: str, scope: str) -> tuple:
    """禁用一个对象. 返回 (ok: bool, message: str, new_path: str).
    obj_type: 'skill' | 'subagent'
    scope: 'user' | 'project'
    """
    if obj_type not in ("skill", "subagent"):
        return False, f"invalid type: {obj_type}", ""
    if scope == "user":
        base = f"{USER_HOME}/.claude"
    elif scope == "project":
        base = f"{PROJECT_ROOT}/.claude"
    else:
        return False, f"invalid scope: {scope}", ""

    if obj_type == "skill":
        src = f"{base}/skills/{name}"
        dst_dir = f"{base}/skills/.disabled"
        dst = f"{dst_dir}/{name}"
        check_src = os.path.isdir(src)
    else:  # subagent
        src = f"{base}/agents/{name}.md"
        dst_dir = f"{base}/agents/.disabled"
        dst = f"{dst_dir}/{name}.md"
        check_src = os.path.isfile(src)

    if not check_src:
        return False, f"源文件不存在: {src}", ""
    if os.path.exists(dst):
        return False, f"目标已存在: {dst}", ""

    try:
        os.makedirs(dst_dir, exist_ok=True)
        os.rename(src, dst)
    except Exception as e:
        return False, f"移动失败: {e}", ""

    # 写入 archive-log.jsonl
    try:
        import json
        log_entry = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "action": "archive",
            "type": obj_type,
            "name": name,
            "scope": scope,
            "src": src,
            "dst": dst,
            "via": "web",
        }
        with open(ARCHIVE_LOG_PATH, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception:
        pass  # 日志失败不影响核心操作

    return True, "已禁用", dst


def restore_object(obj_type: str, name: str, scope: str) -> tuple:
    """从 .disabled/ 恢复一个对象. 返回 (ok, message, new_path)."""
    if scope == "user":
        base = f"{USER_HOME}/.claude"
    elif scope == "project":
        base = f"{PROJECT_ROOT}/.claude"
    else:
        return False, f"invalid scope: {scope}", ""

    if obj_type == "skill":
        src = f"{base}/skills/.disabled/{name}"
        dst = f"{base}/skills/{name}"
        check_src = os.path.isdir(src)
    elif obj_type == "subagent":
        src = f"{base}/agents/.disabled/{name}.md"
        dst = f"{base}/agents/{name}.md"
        check_src = os.path.isfile(src)
    else:
        return False, f"invalid type: {obj_type}", ""

    if not check_src:
        return False, f"禁用目录中未找到: {src}", ""
    if os.path.exists(dst):
        return False, f"目标已存在: {dst}", ""

    try:
        os.rename(src, dst)
    except Exception as e:
        return False, f"恢复失败: {e}", ""

    try:
        import json
        log_entry = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "action": "restore",
            "type": obj_type,
            "name": name,
            "scope": scope,
            "src": src,
            "dst": dst,
            "via": "web",
        }
        with open(ARCHIVE_LOG_PATH, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception:
        pass

    return True, "已恢复", dst


def _serve_static(handler: "Handler", path: str, mime: str):
    if not os.path.isfile(path):
        handler.send_response(404); handler.end_headers(); return
    with open(path, "rb") as f:
        body = f.read()
    handler.send_response(200)
    handler.send_header("Content-Type", mime)
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, data: dict):
        import json
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path not in ("/archive", "/restore", "/clear-summary-cache",
                          "/news/vote", "/news/favorite"):
            self.send_response(404); self.end_headers(); return
        # 中等安全: 拒绝 cloudflare tunnel 转发的写操作
        if not is_direct_local(self.headers):
            self._send_json(403, {
                "ok": False,
                "error": "写操作仅允许本机直连, 不支持通过 cloudflare tunnel 访问"
            })
            return
        if u.path == "/clear-summary-cache":
            n = _clear_summary_cache()
            self._send_json(200, {"ok": True, "cleared": n})
            return

        if u.path == "/news/vote":
            import json as _j
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length > 0 else ""
            try:
                payload = _j.loads(raw) if raw else {}
            except Exception:
                self._send_json(400, {"ok": False, "error": "invalid json body"})
                return
            url = (payload.get("url") or "").strip()
            # 三档 score: "down" / "up" / "star"; null 删除投票
            score = payload.get("score")
            if score not in (None, "down", "up", "star"):
                self._send_json(400, {"ok": False, "error": f"invalid score: {score}"})
                return
            title = (payload.get("title") or "").strip()[:200]
            source = (payload.get("source") or "").strip()[:60]
            if not url:
                self._send_json(400, {"ok": False, "error": "missing url"})
                return
            votes = load_news_votes()
            if score:
                votes[url] = {
                    "ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                    "title": title,
                    "source": source,
                    "score": score,
                }
            else:
                votes.pop(url, None)
            try:
                save_news_votes(votes)
                self._send_json(200, {
                    "ok": True,
                    "score": score,
                    "total": len(votes),
                    "totals_by_score": _counts_by_score(votes),
                })
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return

        if u.path == "/news/favorite":
            import json as _j
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length > 0 else ""
            try:
                payload = _j.loads(raw) if raw else {}
            except Exception:
                self._send_json(400, {"ok": False, "error": "invalid json body"})
                return
            url = (payload.get("url") or "").strip()
            fav = bool(payload.get("fav", True))
            title = (payload.get("title") or "").strip()[:200]
            source = (payload.get("source") or "").strip()[:60]
            if not url:
                self._send_json(400, {"ok": False, "error": "missing url"})
                return
            favs = load_news_favorites()
            if fav:
                favs[url] = {
                    "ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                    "title": title,
                    "source": source,
                }
            else:
                favs.pop(url, None)
            try:
                save_news_favorites(favs)
                self._send_json(200, {"ok": True, "fav": fav, "total": len(favs)})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return

        # 解析 form body
        from urllib.parse import parse_qs as pq
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length > 0 else ""
        form = pq(raw)
        obj_type = form.get("type", [""])[0]
        name = form.get("name", [""])[0]
        scope = form.get("scope", [""])[0]
        if not obj_type or not name or not scope:
            self._send_json(400, {"ok": False, "error": "缺少参数 type/name/scope"})
            return
        if u.path == "/archive":
            ok, msg, new_path = archive_object(obj_type, name, scope)
        else:
            ok, msg, new_path = restore_object(obj_type, name, scope)
        self._send_json(200 if ok else 500, {
            "ok": ok, "message": msg, "path": new_path,
        })

    def do_GET(self):
        u = urlparse(self.path)
        # 静态资源
        if u.path == "/style.css":
            return _serve_static(self, CSS_PATH, "text/css; charset=utf-8")
        if u.path == "/app.js":
            return _serve_static(self, JS_PATH, "application/javascript; charset=utf-8")
        # /news/votes 返回当前所有已投票条目 (url -> entry)
        if u.path == "/news/votes":
            import json
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "votes": load_news_votes(),
            }, ensure_ascii=False).encode("utf-8"))
            return
        # /summary-status 返回今日配额和缓存大小
        if u.path == "/summary-status":
            import json
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(_get_summary_status(), ensure_ascii=False).encode("utf-8"))
            return
        # /prune-list?path=... 生成高刪減收益段落清單 markdown (CLAUDE.md 卡背面)
        if u.path == "/prune-list":
            qs = parse_qs(u.query)
            target = qs.get("path", [""])[0]
            import json
            if not target or not is_path_allowed(target):
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "path not allowed"}).encode("utf-8"))
                return
            try:
                conn2 = sqlite3.connect(DB_FILE)
                weighted_hits = build_weighted_event_counts(conn2)
                known_names = _collect_known_resources(conn2)
                conn2.close()
                analysis = analyze_claude_md(target, known_names, weighted_hits)
                if not analysis:
                    raise RuntimeError("分析失败")
                lines = [f"# {os.path.basename(target)} — 可删减清单", ""]
                count = 0
                for s in analysis["sections"]:
                    if s.get("prune_bucket") == "prune-high":
                        lines.append(f"- ~~{s['heading']}~~ ({s['tokens']} tok)")
                        count += 1
                if count == 0:
                    lines.append("(无高收益段落)")
                md = "\n".join(lines)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "markdown": md, "count": count}, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
            return
        # /summary?path=... 调 Anthropic API 生成中文摘要 (带磁盘缓存)
        if u.path == "/summary":
            qs = parse_qs(u.query)
            target = qs.get("path", [""])[0]
            import json
            if not target or not is_path_allowed(target):
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "path not allowed"}).encode("utf-8"))
                return
            summary, from_cache, err, quota = get_or_generate_summary(target)
            status = 200
            if err:
                status = 429 if "配额" in err or "请求过密" in err else 500
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": not err,
                "summary": summary,
                "cached": from_cache,
                "error": err,
                "quota": quota,
            }, ensure_ascii=False).encode("utf-8"))
            return
        # /open?path=... 在 Mac 上打开文件（白名单内）
        if u.path == "/open":
            qs = parse_qs(u.query)
            target = qs.get("path", [""])[0]
            if not target or not is_path_allowed(target):
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<h1>403</h1><p>path not allowed</p>")
                return
            try:
                subprocess.Popen(["open", target])
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"<h1>500</h1><pre>{html.escape(str(e))}</pre>".encode())
                return
            # 返回一个极简反馈页，2 秒自动关闭
            body = (
                "<!doctype html><meta charset='utf-8'>"
                "<style>body{background:#0a0d12;color:#e6edf3;font-family:-apple-system,sans-serif;"
                "display:flex;align-items:center;justify-content:center;height:100vh;margin:0}"
                ".ok{padding:24px 32px;background:#161b22;border:1px solid #2a313c;border-radius:16px;"
                "text-align:center}.ok h1{color:#3fb950;font-size:18px;margin-bottom:8px}"
                ".ok p{color:#9aa4b2;font-size:13px}</style>"
                "<div class='ok'><h1>✓ 已在 Mac 上打开</h1>"
                f"<p>{html.escape(os.path.basename(target))}</p></div>"
                "<script>setTimeout(()=>history.back(),1500)</script>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            return
        # /mock 路由：返回静态 mock HTML
        if u.path == "/mock":
            if os.path.isfile(MOCK_PATH):
                with open(MOCK_PATH, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404); self.end_headers()
            return
        if u.path != "/":
            self.send_response(404); self.end_headers(); return
        qs = parse_qs(u.query)
        # days 参数兜底：非法值回退到 30，限制在 1-3650 区间
        try:
            days = int(qs.get("days", ["30"])[0])
            if days < 1 or days > 3650:
                days = 30
        except (ValueError, TypeError):
            days = 30
        # Owner 筛选
        owner_filter = qs.get("owner", [""])[0]
        if not os.path.isfile(DB_FILE):
            body = "<h1>暂无数据</h1><p>events.db 不存在。请先正常使用 Claude Code 触发一些工具调用。</p>"
        else:
            try:
                body = render(days, owner_filter=owner_filter)
            except Exception as e:
                import traceback
                body = f"<h1>错误</h1><pre>{html.escape(traceback.format_exc())}</pre>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, fmt, *args):
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 38080
    # HOST 环境变量: 默认 127.0.0.1（仅本机），HOST=0.0.0.0 暴露到 LAN
    host = os.environ.get("USAGE_WEB_HOST", "127.0.0.1")
    print(f"使用统计 dashboard: http://{host}:{port}")
    print(f"DB: {DB_FILE}")
    # ThreadingHTTPServer: 每個請求一個線程, 避免長任務 (claude -p 摘要生成)阻塞其他請求
    from http.server import ThreadingHTTPServer
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    main()
