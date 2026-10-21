from __future__ import annotations

import argparse
import json
import re
import socket
import ssl
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_TITLE = "估值助手 · A股企业评价与估值"
APP_ID = "stock-valuation-local"
DEFAULT_PORT = 8765
CACHE_TTL = 600

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_CACHE: dict[str, tuple[float, dict]] = {}
_LOCK = threading.Lock()

def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent

BASE = base_dir()
WEB_DIR = BASE / "web"
sys.path.insert(0, str(BASE / "src"))

if getattr(sys, "frozen", False):
    import os
    os.environ.setdefault("SVE_DATA_DIR", str(BASE / "data"))

def _search_eastmoney(q: str, count: int = 8) -> list[dict]:
    url = ("https://searchapi.eastmoney.com/api/suggest/get?"
           f"input={urllib.parse.quote(q)}&type=14&count={count}"
           "&token=D43BF722C8E33BDC906FB84D85E326E8")
    req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                               "Referer": "https://www.eastmoney.com/"})
    raw = urllib.request.urlopen(req, timeout=10, context=_CTX).read().decode("utf-8", "ignore")
    data = json.loads(raw)
    items = (data.get("QuotationCodeTable") or {}).get("Data") or []
    out = []
    for it in items:
        code, name = it.get("Code"), it.get("Name")
        if not code or not name or len(code) != 6 or not code.isdigit():
            continue
        if it.get("SecurityTypeName") not in ("沪A", "深A", "京A"):
            continue
        out.append({"code": code, "name": name, "market": it.get("SecurityTypeName")})
    return out[:count]

def _search_tencent(q: str, count: int = 8) -> list[dict]:
    url = f"https://smartbox.gtimg.cn/s3/?v=2&q={urllib.parse.quote(q)}&t=all"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    raw = urllib.request.urlopen(req, timeout=8, context=_CTX).read().decode("utf-8", "ignore")
    m = re.match(r'v_hint="(.*)"', raw.strip())
    if not m:
        return []
    out = []
    for chunk in m.group(1).split("^"):
        parts = chunk.split("~")
        if len(parts) < 5 or parts[4] != "GP-A":
            continue
        mkt, code, name_esc = parts[0], parts[1], parts[2]
        if not (len(code) == 6 and code.isdigit()):
            continue
        try:
            name = json.loads(f'"{name_esc}"')
        except Exception:
            name = name_esc
        out.append({"code": code, "name": name,
                    "market": {"sh": "沪A", "sz": "深A", "bj": "京A"}.get(mkt, mkt)})
    return out[:count]

def search(q: str, count: int = 8) -> list[dict]:
    try:
        items = _search_eastmoney(q, count)
        if items:
            return items
    except Exception:
        pass
    return _search_tencent(q, count)

def valuate(code: str) -> dict:
    hit = _CACHE.get(code)
    if hit and time.time() - hit[0] < CACHE_TTL:
        row = dict(hit[1])
        row["_cached"] = True
        return row

    with _LOCK:
        hit = _CACHE.get(code)
        if hit and time.time() - hit[0] < CACHE_TTL:
            row = dict(hit[1])
            row["_cached"] = True
            return row

        from stock_value_estimator.pipeline import run
        from stock_value_estimator.publish import convert

        t0 = time.time()
        raw = run(code)
        if raw.get("error"):
            raise RuntimeError(raw["error"])
        row = convert(raw)
        row["_elapsed"] = round(time.time() - t0, 1)
        row["_cached"] = False
        _CACHE[code] = (time.time(), row)
        return row

class Handler(BaseHTTPRequestHandler):
    server_version = "StockValuationLocal/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, body: bytes, ctype: str, status: int = 200) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, payload: dict, status: int = 200) -> None:
        self._send(json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", status)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        if parsed.path in ("/", "/index.html"):
            idx = WEB_DIR / "index.html"
            if not idx.exists():
                return self._send("界面文件缺失（web/index.html）".encode("utf-8"),
                                  "text/plain; charset=utf-8", 500)
            return self._send(idx.read_bytes(), "text/html; charset=utf-8")

        if parsed.path == "/api/health":
            return self._json({"ok": True, "app": APP_ID, "cached": len(_CACHE)})

        if parsed.path == "/api/search":
            q = (qs.get("q") or [""])[0].strip()
            if not q:
                return self._json({"ok": True, "items": []})
            try:
                return self._json({"ok": True, "items": search(q)})
            except Exception as e:
                return self._json({"ok": False, "error": f"搜索失败：{e}"}, 502)

        if parsed.path == "/api/valuate":
            code = (qs.get("code") or [""])[0].strip()
            if not (len(code) == 6 and code.isdigit()):
                return self._json({"ok": False, "error": "请输入 6 位股票代码"}, 400)
            try:
                return self._json({"ok": True, "row": valuate(code)})
            except Exception as e:
                return self._json({"ok": False,
                                   "error": f"计算失败：{e}"}, 502)

        self._send(b"not found", "text/plain; charset=utf-8", 404)

class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionAbortedError, BrokenPipeError,
                            ConnectionResetError)):
            return
        super().handle_error(request, client_address)

def _port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True

def _already_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health",
                                    timeout=1.5) as r:
            return json.loads(r.read().decode("utf-8")).get("app") == APP_ID
    except Exception:
        return False

def pick_port(start: int = DEFAULT_PORT, tries: int = 10) -> int:
    for p in range(start, start + tries):
        if _already_running(p):
            return -p
        if not _port_busy(p):
            return p
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

def main() -> int:
    ap = argparse.ArgumentParser(description=APP_TITLE)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = ap.parse_args()

    port = pick_port(args.port)
    if port < 0:
        url = f"http://127.0.0.1:{-port}/"
        print(f"{APP_TITLE}\n\n已有实例正在运行：{url}\n已为你打开浏览器。"
              f"\n（如需重启，先关掉原来的窗口）")
        if not args.no_browser:
            webbrowser.open(url)
        time.sleep(2)
        return 0

    httpd = Server(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"

    print("=" * 58)
    print(f"  {APP_TITLE}")
    print("=" * 58)
    print(f"  地址：{url}")
    print("  浏览器若未自动打开，请手动复制上面这行到浏览器")
    print("  关闭本窗口即退出程序")
    print("=" * 58)

    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")
    finally:
        httpd.server_close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
