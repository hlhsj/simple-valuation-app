from __future__ import annotations

import json

from .base import Provider, http_get
from .eastmoney import query as em_query

FALLBACK_RF = 0.020
FALLBACK_IDX_PCT = 0.50

class RatesProvider(Provider):
    name = "rates"

    def rf_10y(self) -> tuple[float, str, bool]:
        r = em_query("RPTA_WEB_TREASURYYIELD", "", size=1, sort="SOLAR_DATE")
        if not r.get("data"):
            return FALLBACK_RF, "fallback", True
        row = r["data"][0]
        cand = [(k, v) for k, v in row.items()
                if k.startswith("EMM") and isinstance(v, (int, float))]
        cand.sort(key=lambda x: x[1])
        if len(cand) >= 2:
            return cand[-1][1] / 100.0, f"EMM:{cand[-1][0]}", False
        return FALLBACK_RF, "fallback", True

    def hs300_percentile(self) -> tuple[float, float, bool]:
        url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
               "param=sh000300,day,,,1300,qfq")
        try:
            d = json.loads(http_get(url, referer="https://gu.qq.com/"))
        except Exception:
            return FALLBACK_IDX_PCT, 0.0, True
        k = (d.get("data") or {}).get("sh000300", {})
        arr = k.get("qfqday") or k.get("day") or []
        closes = [float(x[2]) for x in arr if len(x) > 2]
        if len(closes) < 200:
            return FALLBACK_IDX_PCT, 0.0, True
        cur = closes[-1]
        pct = sum(1 for c in closes if c < cur) / len(closes)
        return pct, cur, False

_RATES = RatesProvider()

def rf_10y() -> tuple[float, str, bool]:
    return _RATES.rf_10y()

def hs300_percentile() -> tuple[float, float, bool]:
    return _RATES.hs300_percentile()
