from __future__ import annotations

import statistics as st
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

def _item(key: str, label: str, value, score, weight: float, basis: str,
          unit: str, *, note: str | None = None,
          peer_median: float | None = None,
          peer_n: int | None = None) -> dict[str, Any]:
    v = value
    if v is not None and not isinstance(v, str):
        v = float(v)
    return {
        "key": key, "label": label, "value": v,
        "score": None if score is None else float(score),
        "weight": float(weight), "basis": basis, "unit": unit,
        "note": note,
        "peer_median": None if peer_median is None else float(peer_median),
        "peer_n": peer_n,
    }

def _pct(v):
    return None if v is None else v * 100

def _peer_item(key: str, label: str, value, arr: list, higher_better: bool,
               weight: float, unit: str) -> dict[str, Any]:
    xs = [x for x in arr if x is not None]
    med = st.median(xs) if len(xs) >= 3 else None
    return _item(key, label, value, pct_rank(value, arr, higher_better), weight,
                 "peer", unit, peer_median=med, peer_n=len(xs))

def _dim(items: list[dict[str, Any]]) -> float | None:
    return weighted([(it["score"], it["weight"]) for it in items])

def score(latest: dict[str, Any], peers: list[dict[str, Any]],
          goodwill_ratio: float | None, mode: str
          ) -> tuple[dict, float | None, dict, list, dict]:
    fin = latest.get
    pv = lambda k: [p.get(k) for p in peers]

    roe = fin("ROEJQ")
    roic = fin("ROIC")
    w = _w("profit")
    profit_items = [
        _item("roe", "ROE", roe, score_anchors(roe, name="roe"),
              w["roe"], "anchor", "pct"),
        _item("net_margin", "净利率", fin("XSJLL"),
              score_anchors(fin("XSJLL"), name="net_margin"),
              w["net_margin"], "anchor", "pct"),
        _item("gross_margin", "毛利率", fin("XSMLL"),
              score_anchors(fin("XSMLL"), name="gross_margin"),
              w["gross_margin"], "anchor", "pct"),
        _item("roic", "ROIC", roic,
              score_anchors(None if roic is None else roic - 8.0, name="roic_minus_8"),
              w["roic"], "anchor", "pct", note="按 ROIC − 8% 资金成本打分"),
    ]
    profit = _dim(profit_items)

    nco_used = latest.get("_ocf_np_5y")
    nco_note = None
    if nco_used is None:
        nco_used = fin("NCO_NETPROFIT")
        nco_note = "缺 5 年累计数据，降级为当期 OCF/归母"
    fcff, rev = fin("FCFF_FORWARD"), fin("TOTALOPERATEREVE")
    fcf_m = (fcff / rev) if (fcff is not None and rev) else None
    neg_years = latest.get("_neg_cf_years", 0)
    w = _w("cashflow")
    cashflow_items = [
        _item("nco", "现金含量 OCF/净利", nco_used,
              score_anchors(nco_used, name="cash_quality"),
              w["nco"], "anchor", "x", note=nco_note),
        _item("cash_sales", "收现比", fin("XSJXLYYSR"),
              score_anchors(fin("XSJXLYYSR"), name="cash_sales"),
              w["cash_sales"], "anchor", "x"),
        _item("fcf_margin", "FCF 利润率", _pct(fcf_m),
              score_anchors(fcf_m, name="fcf_margin"),
              w["fcf_margin"], "anchor", "pct"),
        _item("stability", "经营现金流为负年数", neg_years,
              cf_stability_score(neg_years), w["stability"], "table", "num"),
    ]
    cashflow = _dim(cashflow_items)

    rev_c, np_c = latest.get("_rev_cagr"), latest.get("_np_cagr")
    npf, kcf = fin("PARENTNETPROFIT"), fin("KCFJCXSYJLR")
    ded = (kcf / npf) if (npf and kcf is not None and npf > 0) else None
    pc_state = (latest.get("_trend") or {}).get("state")
    w = _w("growth")
    growth_items = [
        _item("rev_cagr", "营收 CAGR", _pct(rev_c), score_anchors(rev_c, name="cagr"),
              w["rev_cagr"], "anchor", "pct"),
        _item("np_cagr", "净利 CAGR", _pct(np_c), score_anchors(np_c, name="cagr"),
              w["np_cagr"], "anchor", "pct"),
        _item("rev_yoy_now", "营收同比（最新）", _pct(latest.get("_rev_yoy_now")),
              score_anchors(latest.get("_rev_yoy_now"), name="yoy_now"),
              w["rev_yoy_now"], "anchor", "pct"),
        _item("np_yoy_now", "净利同比（最新）", _pct(latest.get("_np_yoy_now")),
              score_anchors(latest.get("_np_yoy_now"), name="yoy_now"),
              w["np_yoy_now"], "anchor", "pct"),
        _item("cash_quality", "增长的现金支撑", nco_used,
              score_anchors(nco_used, name="cash_quality_growth"),
              w["cash_quality"], "anchor", "x"),
        _item("deduct_ratio", "扣非/归母", ded,
              score_anchors(ded, name="deduct_ratio"),
              w["deduct_ratio"], "anchor", "x"),
        _item("consistency", "趋势一致性", pc_state,
              trend_consistency_score(pc_state), w["consistency"], "table", "text"),
    ]
    growth = _dim(growth_items)

    bank_fields = (fin("NEWCAPITALADER"), fin("NONPERLOAN"), fin("BLDKBBL"))
    is_bank = mode == "资本型" and any(x is not None for x in bank_fields)
    w = _w("solvency")
    if is_bank:
        solvency_items = [
            _item("car_solvency", "资本充足率", fin("NEWCAPITALADER"),
                  score_anchors(fin("NEWCAPITALADER"), name="car_solvency"),
                  1.0, "anchor", "pct", note="银行口径，替代流动比率"),
        ]
    else:
        solvency_items = [
            _peer_item("current_ratio", "流动比率", fin("LD"), pv("LD"), True,
                       w["current_ratio"], "x"),
            _item("quick_ratio", "速动比率", fin("SD"),
                  score_anchors(fin("SD"), name="quick_ratio"),
                  w["quick_ratio"], "anchor", "x"),
            _item("cash_ratio", "现金比率", fin("CASH_RATIO"),
                  score_anchors(fin("CASH_RATIO"), name="cash_ratio"),
                  w["cash_ratio"], "anchor", "x"),
            _item("interest_cover", "利息保障倍数", fin("INTEREST_COVERAGE_RATIO"),
                  score_anchors(fin("INTEREST_COVERAGE_RATIO"), name="interest_cover"),
                  w["interest_cover"], "anchor", "x"),
        ]
    solvency = _dim(solvency_items)

    w = _w("operation")
    operation_items = [
        _peer_item("asset_turnover", "总资产周转率", fin("TOAZZL"), pv("TOAZZL"), True,
                   w["asset_turnover"], "x"),
        _peer_item("inv_days", "存货周转天数", fin("CHZZTS"), pv("CHZZTS"), False,
                   w["inv_days"], "days"),
        _peer_item("ar_days", "应收周转天数", fin("YSZKZZTS"), pv("YSZKZZTS"), False,
                   w["ar_days"], "days"),
        _peer_item("ap_days", "应付周转天数", fin("PAYABLE_TDAYS"), pv("PAYABLE_TDAYS"), True,
                   w["ap_days"], "days"),
        _peer_item("ccc", "现金周期", fin("OPERATE_CYCLE"), pv("OPERATE_CYCLE"), False,
                   w["ccc"], "days"),
    ]
    operation = _dim(operation_items)

    liab = fin("LIABILITY")
    int_debt = latest.get("_int_debt")
    ib = (int_debt / liab) if (int_debt is not None and liab and liab > 0) else None
    if is_bank:
        wb = _w("asset_bank")
        asset_items = [
            _item("npl", "不良贷款率", fin("NONPERLOAN"),
                  score_anchors(fin("NONPERLOAN"), name="npl"), wb["npl"], "anchor", "pct"),
            _item("provision", "拨备覆盖率", fin("BLDKBBL"),
                  score_anchors(fin("BLDKBBL"), name="provision"),
                  wb["provision"], "anchor", "pct"),
            _item("car", "资本充足率", fin("NEWCAPITALADER"),
                  score_anchors(fin("NEWCAPITALADER"), name="car"),
                  wb["car"], "anchor", "pct"),
        ]
        ib = None
    else:
        wg = _w("asset_general")
        asset_items = [
            _peer_item("debt_ratio", "资产负债率", fin("ZCFZL"), pv("ZCFZL"), False,
                       wg["debt_ratio"], "pct"),
            _item("int_debt_ratio", "有息负债率", _pct(ib),
                  score_anchors(ib, name="int_debt_ratio"),
                  wg["int_debt_ratio"], "anchor", "pct"),
            _item("goodwill_ratio", "商誉/净资产", _pct(goodwill_ratio),
                  score_anchors(goodwill_ratio, name="goodwill_ratio"),
                  wg["goodwill_ratio"], "anchor", "pct"),
        ]
    asset = _dim(asset_items)

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

    items_by_dim = {"profit": profit_items, "cashflow": cashflow_items,
                    "growth": growth_items, "solvency": solvency_items,
                    "operation": operation_items, "asset": asset_items}
    for items in items_by_dim.values():
        tot = sum(it["weight"] for it in items) or 1.0
        for it in items:
            it["weight"] = round(it["weight"] / tot, 4)
    breakdown = {
        k: {"score": dims[k], "weight": dw.get(k, 0.0), "items": items_by_dim[k]}
        for k in dims
    }
    return dims, total, details, missing, breakdown

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
