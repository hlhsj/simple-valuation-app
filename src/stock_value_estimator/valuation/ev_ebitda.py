from __future__ import annotations

import statistics as st
from typing import Any, Sequence

from ..config import params

P = params()

def _row(rows: dict[str, list[str]] | None, names: Sequence[str]) -> list[str] | None:
    for n in names:
        if rows and n in rows:
            return rows[n]
    return None

def _num(row: Sequence[str] | None, i: int) -> float | None:
    if row is None or i >= len(row):
        return None
    try:
        return float(str(row[i]).replace(",", ""))
    except (TypeError, ValueError):
        return None

def _pick(row: Sequence[str] | None, periods: Sequence[str], date: str) -> float | None:
    if row is None:
        return None
    for i, p in enumerate(periods):
        if p == date:
            return _num(row, i)
    return None

def ebitda_ttm(cf: dict | None, cfp: Sequence[str],
               pl: dict | None, plp: Sequence[str]) -> dict[str, Any]:
    dep = _row(cf, ["固定资产折旧、油气资产折耗、生产性物资折旧",
                    "固定资产折旧"])
    am1 = _row(cf, ["无形资产摊销"])
    am2 = _row(cf, ["长期待摊费用摊销"])
    tp = _row(pl, ["四、利润总额", "三、利润总额"])
    fin = _row(pl, ["财务费用"])

    def one(date: str) -> float | None:
        t = _pick(tp, plp, date)
        if t is None:
            return None
        d = _pick(dep, cfp, date) or 0.0
        a = (_pick(am1, cfp, date) or 0.0) + (_pick(am2, cfp, date) or 0.0)
        f = max(_pick(fin, plp, date) or 0.0, 0.0)
        return t + f + d + a

    periods = plp or []
    latest = periods[0] if periods else None
    if not latest:
        return {"ok": False, "reason": "无利润表数据"}
    cur = one(latest)
    if cur is None:
        return {"ok": False, "reason": "利润总额不可得"}

    if latest.endswith("1231"):
        return {"ok": True, "ttm": cur, "period": latest, "basis": "年报口径"}

    yr = latest[:4]
    fy, pyh = f"{int(yr)-1}1231", f"{int(yr)-1}{latest[4:]}"
    a, b = one(fy), one(pyh)
    if a is None or b is None:
        return {"ok": True, "ttm": cur * 2, "period": latest,
                "basis": "中报年化（缺上年同期，×2 近似）"}
    return {"ok": True, "ttm": cur + a - b, "period": latest,
            "basis": f"TTM = {latest} + {fy} − {pyh}"}

def net_debt(bs: dict | None) -> float | None:
    if not bs:
        return None
    keys = ["短期借款", "一年内到期的非流动负债", "长期借款",
            "应付债券", "租赁负债"]
    debt = 0.0
    for k in keys:
        v = _num(_row(bs, [k]), 0)
        debt += v or 0.0
    cash = _num(_row(bs, ["货币资金"]), 0)
    if cash is None:
        return None
    return debt - cash

def capital_intensity(cf: dict | None, cfp: Sequence[str],
                      pl: dict | None, plp: Sequence[str],
                      bs: dict | None) -> dict[str, float | None]:
    dep = _num(_row(cf, ["固定资产折旧、油气资产折耗、生产性物资折旧",
                         "固定资产折旧"]), 0) or 0.0
    am1 = _num(_row(cf, ["无形资产摊销"]), 0) or 0.0
    rev = _num(_row(pl, ["一、营业总收入", "营业总收入"]), 0)
    fixed = _num(_row(bs, ["固定资产净额", "固定资产及清理(合计)",
                           "固定资产"]), 0) or 0.0
    total = _num(_row(bs, ["资产总计", "资产合计"]), 0) or 0.0
    da = dep + am1
    return {
        "da_rev": (da / rev) if rev else None,
        "fixed_asset": (fixed / total) if total > 0 else None,
    }

def industry_band(industry_label: str | None) -> tuple[float, float]:
    bands = P.get("ev_ebitda", {}).get("bands", {})
    default = bands.get("default", [8.0, 15.0])
    if not industry_label:
        return default[0], default[1]
    lab = industry_label or ""
    for k, v in bands.items():
        if k != "default" and lab.startswith(k):
            return v[0], v[1]
    return default[0], default[1]

def fair_multiple(r: float, g: float, industry_label: str | None) -> tuple[float, str]:
    lo, hi = industry_band(industry_label)
    if r - g > 0.005:
        cap = 1.0 / (r - g)
        m = min(max(cap, lo), hi)
        note = f"资本化倍数 1/(r−g) = {cap:.1f}×，夹紧至行业区间 [{lo:g}, {hi:g}] → {m:.1f}×"
    else:
        m = hi
        note = f"r−g ≤ 0.5pp 资本化倍数失效，取行业区间上限 {hi:g}×"
    return m, note

def value(ebitda_ttm_: float | None, net_debt_: float | None,
          shares: float | None, r: float, g: float,
          industry_label: str | None) -> dict[str, Any]:
    if not ebitda_ttm_ or ebitda_ttm_ <= 0:
        return {"applicable": False, "reason": "EBITDA ≤ 0 或不可得"}
    if not shares or shares <= 0:
        return {"applicable": False, "reason": "总股本不可得"}
    m, note = fair_multiple(r, g, industry_label)
    ev = m * ebitda_ttm_
    equity = ev - (net_debt_ or 0.0)
    if equity <= 0:
        return {"applicable": False,
                "reason": f"净债务（{net_debt_/1e8:.0f} 亿）已超过企业价值"
                          f"（{ev/1e8:.0f} 亿），股权价值为负——资本结构风险过高，不出价"}
    per_share = equity / shares
    return {"applicable": True, "mult": m, "mult_note": note,
            "ebitda": ebitda_ttm_, "ev": ev, "net_debt": net_debt_,
            "equity": equity, "shares": shares, "target": per_share}

def should_degrade(primary: str, pe_now: float | None, eps_ttm: float | None,
                   intensity: dict[str, float | None] | None) -> tuple[bool, str]:
    if primary != "PE":
        return False, ""
    cfg = P.get("ev_ebitda", {}).get("trigger", {})
    pe_hi, eps_lo = cfg.get("pe_high", 80), cfg.get("eps_low", 0.1)
    dep_rev, fa = cfg.get("dep_rev", 0.15), cfg.get("fixed_asset", 0.40)

    micro = False
    if pe_now is not None and pe_now > pe_hi:
        micro = True
    if eps_ttm is not None and eps_ttm < eps_lo:
        micro = True
    if not micro:
        return False, ""

    inten = intensity or {}
    da_rev, fixed = inten.get("da_rev"), inten.get("fixed_asset")
    if da_rev is not None and da_rev > dep_rev:
        return True, f"PE 口径失效且折旧摊销/营收达 {da_rev:.0%}（>{dep_rev:.0%}），属重资产微利"
    if fixed is not None and fixed > fa:
        return True, f"PE 口径失效且固定资产/总资产达 {fixed:.0%}（>{fa:.0%}），属重资产微利"
    return False, ""

__all__ = [
    "ebitda_ttm", "net_debt", "capital_intensity", "industry_band",
    "fair_multiple", "value", "should_degrade",
]
