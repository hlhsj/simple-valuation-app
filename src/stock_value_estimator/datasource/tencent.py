from __future__ import annotations

from typing import Any

from .base import Provider, http_get

class TencentProvider(Provider):
    name = "tencent"

    def quote(self, code: str) -> dict[str, Any] | None:
        prefix = "sh" if code[0] in "69" else "sz"
        txt = http_get(f"https://qt.gtimg.cn/q={prefix}{code}",
                       encoding="gbk", referer="https://gu.qq.com/")
        p = txt.split("~")
        if len(p) < 50:
            return None
        try:
            return {
                "code": code,
                "name": p[1],
                "price": float(p[3]) if p[3] else None,
                "pe": float(p[39]) if p[39] else None,
                "pb": float(p[46]) if p[46] else None,
                "mktcap_yi": float(p[45]) if p[45] else None,
                "turnover": float(p[38]) if p[38] else None,
            }
        except (ValueError, IndexError):
            return None

_TENCENT = TencentProvider()

def quote(code: str) -> dict[str, Any] | None:
    return _TENCENT.quote(code)
