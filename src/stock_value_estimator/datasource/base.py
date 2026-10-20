from __future__ import annotations

import json
import ssl
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from ..config import params

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

@dataclass
class SourceStatus:
    provider: str
    ok: bool
    confidence: float = 1.0
    note: str = ""
    degraded: bool = False

@dataclass
class FetchResult:
    data: Any = None
    status: SourceStatus = field(default_factory=lambda: SourceStatus("unknown", False))

def http_get(url: str, encoding: str = "utf-8", referer: str | None = None,
             timeout: int | None = None, retries: int | None = None) -> str:
    cfg = params().get("http", {})
    timeout = timeout if timeout is not None else cfg.get("timeout", 15)
    retries = retries if retries is not None else cfg.get("retries", 2)
    last: Exception | None = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Referer": referer or "https://data.eastmoney.com/",
            })
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.read().decode(encoding, "ignore")
        except Exception as e:
            last = e
            if i == retries:
                break
            time.sleep(0.6 * (i + 1))
    raise RuntimeError(f"请求失败：{url}") from last

def throttle() -> None:
    time.sleep(params().get("http", {}).get("throttle", 0.3))

class Provider:

    name: str = "base"

    def fetch_json(self, url: str, **kw) -> Any:
        txt = http_get(url, **kw)
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            return None
