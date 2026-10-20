from __future__ import annotations

import json
import time
import urllib.parse
from typing import Any, Iterable

from .base import Provider, http_get

API = "https://datacenter-web.eastmoney.com/api/data/v1/get"

BATCH_COLS = (
    "SECURITY_CODE,ROEJQ,XSJLL,XSMLL,ROIC,NCO_NETPROFIT,XSJXLYYSR,LD,SD,"
    "CASH_RATIO,INTEREST_COVERAGE_RATIO,ZCFZL,TOAZZL,CHZZTS,YSZKZZTS,"
    "PAYABLE_TDAYS,OPERATE_CYCLE,TOTALOPERATEREVE,INTEREST_DEBT_RATIO,"
    "TOTAL_ASSETS_PK,LIABILITY,PARENTNETPROFIT"
)

class EastmoneyProvider(Provider):
    name = "eastmoney"

    def query(self, report: str, filter_: str = "", columns: str = "ALL",
              page: int = 1, size: int = 50, sort: str | None = None,
              desc: bool = True) -> dict[str, Any]:
        q = {
            "reportName": report, "columns": columns,
            "pageNumber": page, "pageSize": size,
            "source": "WEB", "client": "WEB",
        }
        if filter_:
            q["filter"] = filter_
        if sort:
            q["sortColumns"] = sort
            q["sortTypes"] = "-1" if desc else "1"
        url = API + "?" + urllib.parse.urlencode(q)
        try:
            d = json.loads(http_get(url))
        except Exception:
            return {"success": False, "data": [], "pages": 0, "count": 0}
        r = d.get("result") or {}
        return {"success": d.get("success"), "data": r.get("data") or [],
                "pages": r.get("pages") or 0, "count": r.get("count") or 0}

    def f10_periods(self, code: str, periods: int = 14) -> list[dict[str, Any]]:
        return self.query("RPT_F10_FINANCE_MAINFINADATA",
                          f'(SECURITY_CODE="{code}")', size=periods,
                          sort="REPORT_DATE")["data"]

    def f10_batch(self, codes: Iterable[str], report_date: str,
                  chunk: int = 45) -> list[dict[str, Any]]:
        codes = list(codes)
        out: list[dict[str, Any]] = []
        for i in range(0, len(codes), chunk):
            part = codes[i:i + chunk]
            inlist = ",".join(f'"{c}"' for c in part)
            f = f'(SECURITY_CODE in ({inlist}))(REPORT_DATE=\'{report_date}\')'
            out.extend(self.query("RPT_F10_FINANCE_MAINFINADATA", f,
                                  columns=BATCH_COLS, size=60)["data"])
            time.sleep(0.3)
        return out

    def valuation_history(self, code: str, size: int = 1400) -> list[dict[str, Any]]:
        return self.query("RPT_VALUEANALYSIS_DET", f'(SECURITY_CODE="{code}")',
                          size=size, sort="TRADE_DATE")["data"]

    def dividends(self, code: str) -> list[dict[str, Any]]:
        return self.query("RPT_SHAREBONUS_DET", f'(SECURITY_CODE="{code}")',
                          size=60, sort="REPORT_DATE")["data"]

    def pledge(self, code: str) -> dict[str, Any] | None:
        r = self.query("RPT_CSDC_LIST", f'(SECURITY_CODE="{code}")',
                       size=1, sort="TRADE_DATE")["data"]
        return r[0] if r else None

    def lift_stage(self, code: str) -> list[dict[str, Any]]:
        return self.query("RPT_LIFT_STAGE", f'(SECURITY_CODE="{code}")',
                          size=60, sort="FREE_DATE")["data"]

    def holder_pledge(self, code: str) -> list[dict[str, Any]]:
        return self.query("RPTA_APP_ACCUMDETAILS", f'(SECURITY_CODE="{code}")',
                          size=300, sort="NOTICE_DATE")["data"]

    def controller(self, code: str) -> list[str]:
        mk = ("SH" if code[0] in "69" else "BJ" if code[0] in "48" else "SZ")
        url = ("https://emweb.securities.eastmoney.com/PC_HSF10/"
               f"ShareholderResearch/PageAjax?code={mk}{code}")
        try:
            raw = http_get(url, referer="https://emweb.securities.eastmoney.com/")
            d = json.loads(raw)
        except Exception:
            return []
        names: list[str] = []
        for row in (d.get("sjkzr") or []):
            for part in str(row.get("HOLDER_NAME") or "").split(","):
                p = part.strip()
                if p:
                    names.append(p)
        return names

_EASTMONEY = EastmoneyProvider()

def query(*a, **kw):
    return _EASTMONEY.query(*a, **kw)

def f10_periods(code: str, periods: int = 14) -> list[dict[str, Any]]:
    return _EASTMONEY.f10_periods(code, periods)

def f10_batch(codes: Iterable[str], report_date: str) -> list[dict[str, Any]]:
    return _EASTMONEY.f10_batch(codes, report_date)

def valuation_history(code: str, size: int = 1400) -> list[dict[str, Any]]:
    return _EASTMONEY.valuation_history(code, size)

def dividends(code: str) -> list[dict[str, Any]]:
    return _EASTMONEY.dividends(code)

def pledge(code: str) -> dict[str, Any] | None:
    return _EASTMONEY.pledge(code)

def lift_stage(code: str) -> list[dict[str, Any]]:
    return _EASTMONEY.lift_stage(code)

def holder_pledge(code: str) -> list[dict[str, Any]]:
    return _EASTMONEY.holder_pledge(code)

def controller(code: str) -> list[str]:
    return _EASTMONEY.controller(code)
