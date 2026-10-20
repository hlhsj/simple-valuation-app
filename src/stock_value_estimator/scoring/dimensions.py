from __future__ import annotations

from typing import Any

from ..config import weights as weights_cfg
from .anchors import (
    cf_stability_score,
    pct_rank,
    score_anchors,
    trend_consistency_score,
    weighted,
)

W = weights_cfg()

def _w(section: str) -> dict[str, float]:
    return W.get(section) or {}

def score(latest: dict[str, Any], peers: list[dict[str, Any]],
          goodwill_ratio: float | None, mode: str) -> tuple[dict, float | None, dict]:
    fin = latest.get
    pv = lambda k: [p.get(k) for p in peers]

    roe = fin("ROEJQ")
    roic = fin("ROIC")
    s_roe = score_anchors(roe, name="roe")
    s_nm = score_anchors(fin("XSJLL"), name="net_margin")
    s_gm = score_anchors(fin("XSMLL"), name="gross_margin")
    s_roic = score_anchors(None if roic is None else roic - 8.0, name="roic_minus_8")
    w = _w("profit")
    profit = weighted([(s_roe, w["roe"]), (s_nm, w["net_margin"]),
                       (s_gm, w["gross_margin"]), (s_roic, w["roic"])])

    nco_used = latest.get("_ocf_np_5y")
    if nco_used is None:
        nco_used = fin("NCO_NETPROFIT")
    fcff, rev = fin("FCFF_FORWARD"), fin("TOTALOPERATEREVE")
    fcf_m = (fcff / rev) if (fcff is not None and rev) else None
    s_nco = score_anchors(nco_used, name="cash_quality")
    s_cr = score_anchors(fin("XSJXLYYSR"), name="cash_sales")
    s_fcf = score_anchors(fcf_m, name="fcf_margin")
    s_stab = cf_stability_score(latest.get("_neg_cf_years", 0))
    w = _w("cashflow")
    cashflow = weighted([(s_nco, w["nco"]), (s_cr, w["cash_sales"]),
                         (s_fcf, w["fcf_margin"]), (s_stab, w["stability"])])

    rev_c, np_c = latest.get("_rev_cagr"), latest.get("_np_cagr")
    s_rev = score_anchors(rev_c, name="cagr")
    s_np = score_anchors(np_c, name="cagr")
    s_rev_now = score_anchors(latest.get("_rev_yoy_now"), name="yoy_now")
    s_np_now = score_anchors(latest.get("_np_yoy_now"), name="yoy_now")
    npf, kcf = fin("PARENTNETPROFIT"), fin("KCFJCXSYJLR")
    ded = (kcf / npf) if (npf and kcf is not None and npf > 0) else None
    s_ded = score_anchors(ded, name="deduct_ratio")
    s_qual = score_anchors(nco_used, name="cash_quality_growth")
    s_cons = trend_consistency_score((latest.get("_trend") or {}).get("state"))
    w = _w("growth")
    growth = weighted([(s_rev, w["rev_cagr"]), (s_np, w["np_cagr"]),
                       (s_rev_now, w["rev_yoy_now"]), (s_np_now, w["np_yoy_now"]),
                       (s_qual, w["cash_quality"]), (s_ded, w["deduct_ratio"]),
                       (s_cons, w["consistency"])])

    bank_fields = (fin("NEWCAPITALADER"), fin("NONPERLOAN"), fin("BLDKBBL"))
    is_bank = mode == "资本型" and any(x is not None for x in bank_fields)
    if is_bank:
        s_ld = s_sd = s_int = None
        s_cr2 = score_anchors(fin("NEWCAPITALADER"), name="car_solvency")
    else:
        s_ld = pct_rank(fin("LD"), pv("LD"), True)
        s_sd = score_anchors(fin("SD"), name="quick_ratio")
        s_cr2 = score_anchors(fin("CASH_RATIO"), name="cash_ratio")
        s_int = score_anchors(fin("INTEREST_COVERAGE_RATIO"), name="interest_cover")
    w = _w("solvency")
    solvency = weighted([(s_ld, w["current_ratio"]), (s_sd, w["quick_ratio"]),
                         (s_cr2, w["cash_ratio"]), (s_int, w["interest_cover"])])

    o_to = pct_rank(fin("TOAZZL"), pv("TOAZZL"), True)
    o_inv = pct_rank(fin("CHZZTS"), pv("CHZZTS"), False)
    o_ar = pct_rank(fin("YSZKZZTS"), pv("YSZKZZTS"), False)
    o_ap = pct_rank(fin("PAYABLE_TDAYS"), pv("PAYABLE_TDAYS"), True)
    o_ccc = pct_rank(fin("OPERATE_CYCLE"), pv("OPERATE_CYCLE"), False)
    w = _w("operation")
    operation = weighted([(o_to, w["asset_turnover"]), (o_inv, w["inv_days"]),
                          (o_ar, w["ar_days"]), (o_ap, w["ap_days"]), (o_ccc, w["ccc"])])

    liab = fin("LIABILITY")
    int_debt = latest.get("_int_debt")
    ib = (int_debt / liab) if (int_debt is not None and liab and liab > 0) else None
    if is_bank:
        s_npl = score_anchors(fin("NONPERLOAN"), name="npl")
        s_prov = score_anchors(fin("BLDKBBL"), name="provision")
        s_car2 = score_anchors(fin("NEWCAPITALADER"), name="car")
        wb = _w("asset_bank")
        asset = weighted([(s_npl, wb["npl"]), (s_prov, wb["provision"]), (s_car2, wb["car"])])
        ib = None
    else:
        a_dr = pct_rank(fin("ZCFZL"), pv("ZCFZL"), False)
        a_ibd = score_anchors(ib, name="int_debt_ratio")
        a_gw = score_anchors(goodwill_ratio, name="goodwill_ratio")
        wg = _w("asset_general")
        asset = weighted([(a_dr, wg["debt_ratio"]), (a_ibd, wg["int_debt_ratio"]),
                          (a_gw, wg["goodwill_ratio"])])

    dims = {"profit": profit, "cashflow": cashflow, "growth": growth,
            "solvency": solvency, "operation": operation, "asset": asset}
    dw = W.get("dimensions") or {}
    total = weighted([(v, dw.get(k, 0)) for k, v in dims.items()])
    missing = [k for k, v in dims.items() if v is None]

    details = {
        "roe": roe, "net_margin": fin("XSJLL"), "gross_margin": fin("XSMLL"), "roic": roic,
        "nco": fin("NCO_NETPROFIT"), "cash_sales": fin("XSJXLYYSR"), "fcf_margin": fcf_m,
        "rev_cagr": rev_c, "np_cagr": np_c, "deduct_ratio": ded,
        "growth_std": latest.get("_growth_std"),
        "rev_yoy_now": latest.get("_rev_yoy_now"), "np_yoy_now": latest.get("_np_yoy_now"),
        "np_yoy_annual": latest.get("_np_yoy_annual"),
        "np_down_years": latest.get("_np_down_years"),
        "ocf_np_5y": latest.get("_ocf_np_5y"), "ocf_yoy": latest.get("_ocf_yoy"),
        "pc_state": latest.get("_pc_state"), "pc_why": latest.get("_pc_why"),
        "current_ratio": fin("LD"), "quick_ratio": fin("SD"), "cash_ratio": fin("CASH_RATIO"),
        "interest_cover": fin("INTEREST_COVERAGE_RATIO"), "debt_ratio": fin("ZCFZL"),
        "int_debt_ratio": ib, "goodwill_ratio": goodwill_ratio,
        "asset_turnover": fin("TOAZZL"), "inv_days": fin("CHZZTS"),
        "ar_days": fin("YSZKZZTS"), "ap_days": fin("PAYABLE_TDAYS"), "ccc": fin("OPERATE_CYCLE"),
        "npl": fin("NONPERLOAN"), "prov": fin("BLDKBBL"), "car": fin("NEWCAPITALADER"),
        "bank_metric": is_bank,
    }
    return dims, total, details, missing

def grade(total: float | None) -> tuple[str, float]:
    from ..config import params
    p = params()
    g, m = p.get("grade", {}), p.get("mos", {})
    if total is None:
        return "N/A", m.get("D", 0.35)
    if total >= g.get("A", 80):
        return "A", m.get("A", 0.20)
    if total >= g.get("B", 70):
        return "B", m.get("B", 0.25)
    if total >= g.get("C", 50):
        return "C", m.get("C", 0.30)
    return "D", m.get("D", 0.35)

def dupont(latest: dict[str, Any]) -> dict[str, Any] | None:
    nm, at, em_ = latest.get("XSJLL"), latest.get("TOAZZL"), latest.get("QYCS")
    if not (nm and at and em_):
        return None
    if nm >= 20:
        driver = "高净利率"
    elif at >= 1.0:
        driver = "高周转率"
    elif em_ >= 2.5:
        driver = "高权益乘数"
    else:
        driver = "均衡型"
    return {"roe_calc": nm / 100 * at * em_ * 100, "net_margin": nm,
            "asset_turnover": at, "equity_multiplier": em_, "driver": driver}
