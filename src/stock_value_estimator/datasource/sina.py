from __future__ import annotations

from typing import Any

from .base import Provider, http_get

KINDS = ("BalanceSheet", "ProfitStatement", "CashFlow")

class SinaProvider(Provider):
    name = "sina"

    def table(self, code: str, kind: str) -> tuple[dict[str, list[str]], list[str]]:
        if kind not in KINDS:
            raise ValueError(f"未知表类型：{kind}，可选 {KINDS}")
        url = (f"https://money.finance.sina.com.cn/corp/go.php/vDOWN_{kind}"
               f"/displaytype/4/stockid/{code}/ctrl/all.phtml")
        txt = http_get(url, encoding="gbk", referer="https://finance.sina.com.cn/")
        lines = [ln for ln in txt.splitlines() if ln.strip()]
        if not lines:
            return {}, []
        periods = [x.strip() for x in lines[0].split("\t")[1:]]
        rows: dict[str, list[str]] = {}
        for ln in lines[2:]:
            parts = [x.strip() for x in ln.split("\t")]
            if len(parts) < 2:
                continue
            rows[parts[0]] = parts[1:]
        return rows, periods

_SINA = SinaProvider()

def table(code: str, kind: str) -> tuple[dict[str, Any], list[str]]:
    return _SINA.table(code, kind)

def balance_sheet(code: str):
    return table(code, "BalanceSheet")

def profit_statement(code: str):
    return table(code, "ProfitStatement")

def cash_flow(code: str):
    return table(code, "CashFlow")
