from __future__ import annotations

import statistics as st
import time
from datetime import datetime, timedelta
from typing import Any

from . import datasource as ds
from .config import params
from .decision import calc_expected_return, judge, market_state, position_suggestion
from .profile import classify_mode, five_forces_analyze, judge_lifecycle, profit_cash_check, trend_inflection
from .screening import screen
from .screening.red_flags import (
    ar_inventory_growth,
    first_value,
    gross_margin_std,
    int_debt as calc_int_debt,
    neg_cf_years,
    pledge_pressure,
    profit_crashes,
    quarter_yoy,
    quarterly_profile,
    unlock_pressure,
)
from .scoring import grade, score as six_dim_score
from .scoring.anchors import cagr
from .scoring.peer import peers_of
from .valuation import ev_ebitda
from .valuation import channel
from .valuation import evaluate as valuate

P = params()

HIST_YEARS = 5

def _payout(annuals: list[dict[str, Any]], divs: list[dict[str, Any]]
            ) -> tuple[float, list[dict[str, Any]], float | None]:
    year_dps: dict[str, float] = {}
    for d in divs:
        if d.get("ASSIGN_PROGRESS") != "实施分配":
            continue
        rd = (d.get("REPORT_DATE") or "")[:10]
        per10 = d.get("PRETAX_BONUS_RMB")
        if rd and per10:
            year_dps[rd[:4]] = year_dps.get(rd[:4], 0.0) + per10 / 10.0
    payouts: list[float] = []
    used: list[dict[str, Any]] = []
    for a in annuals:
        y = (a.get("REPORT_DATE") or "")[:4]
        eps = a.get("EPSJB")
        if y in year_dps and eps and eps > 0:
            b = year_dps[y] / eps
            if 0 <= b <= 1.5:
                payouts.append(min(b, 1.0))
                used.append({"year": y, "dps": round(year_dps[y], 3),
                             "eps": round(eps, 3), "payout": round(b, 3)})
        if len(payouts) >= HIST_YEARS:
            break
    b_avg = st.mean(payouts) if payouts else 0.30
    dps_latest = year_dps.get((annuals[0].get("REPORT_DATE") or "")[:4]) if annuals else None
    return b_avg, used, dps_latest

def _ocf_quality(cf_rows: dict[str, list[str]] | None, cf_periods: list[str] | None,
                 pl_rows: dict[str, list[str]] | None,
                 pl_periods: list[str] | None) -> tuple[float | None, float | None, float | None]:
    def row_of(rows: dict[str, list[str]] | None, names: list[str]) -> list[str] | None:
        if not rows:
            return None
        for n in names:
            if n in rows:
                return rows[n]
            for k in rows:
                if n in k:
                    return rows[k]
        return None

    def series(rows, periods, names):
        r = row_of(rows, names)
        if not r or not periods:
            return []
        out = []
        for i, p in enumerate(periods):
            if p.endswith("1231") and i < len(r):
                try:
                    out.append((p[:4], float(r[i].replace(",", ""))))
                except ValueError:
                    pass
        return out

    ocf = series(cf_rows, cf_periods, ["经营活动产生的现金流量净额", "经营活动产生现金流量净额"])
    npf = series(pl_rows, pl_periods, ["归属于母公司所有者的净利润", "归属于母公司股东的净利润"])
    np_map = dict(npf)
    pairs = [(y, o, np_map[y]) for y, o in ocf if y in np_map][:HIST_YEARS]
    tot = sum(n for _, _, n in pairs)
    q5 = (sum(o for _, o, _ in pairs) / tot) if (pairs and tot > 0) else None
    ocf_yoy = (ocf[0][1] / ocf[1][1] - 1) if len(ocf) >= 2 and ocf[1][1] else None
    np_yoy = (npf[0][1] / npf[1][1] - 1) if len(npf) >= 2 and npf[1][1] else None
    return q5, ocf_yoy, np_yoy

def _band_and_px(ch: dict, unit: float | None, keys: tuple[str, str, str]):
    band = {out: ch.get(src) for out, src in zip(("p20", "p50", "p80"), keys)}
    px = {k: (v * unit if (v and unit) else None) for k, v in band.items()}
    return band, px

def _build_channel(val: dict, rt: dict, bps: float | None,
                   hist: list) -> dict:
    primary = val.get("primary")
    model = "PE" if primary == "PE" else ("PB" if primary == "PB" else None)
    if model is None:
        return {"model": primary, "applicable": False,
                "reason": "EV/EBITDA 与回避类模型不依赖历史估值通道，去泡沫不适用"}

    unit = val.get("eps_ttm") if model == "PE" else bps
    ch = val.get("pe_ch") if model == "PE" else val.get("pb_ch")
    keys = ("p20", "p50", "p80") if model == "PE" else ("b20", "b50", "b80")
    band, px = _band_and_px(ch or {}, unit, keys)
    out: dict = {
        "applicable": True,
        "model": model,
        "unit": unit,
        "window_years": HIST_YEARS,
        "n": (ch or {}).get("n"),
        "current": rt.get("pe") if model == "PE" else rt.get("pb"),
        "cur_pct": val.get("cur_pct") if model == "PE" else val.get("pb_pct"),
        "band": band,
        "px": px,
        "series": channel.series(hist, "PE_TTM" if model == "PE" else "PB_MRQ"),
        "debubble": {"applicable": False, "reason": "该样本未产出公平价，无法二次估值"},
    }
    db_cfg = P.get("debubble", {})
    out["debubble"] = {
        "can": bool(val.get("target")),
        "years": float(db_cfg.get("years", 3)),
        "cut_top": float(db_cfg.get("cut_top", 0.9)),
        "reason": None if val.get("target") else "该样本未产出公平价，无法二次估值",
    }
    return out

def debubble_revalue(d: dict) -> dict | None:
    ctx = d.get("_ctx")
    val = d.get("valuation") or {}
    if not ctx or not val.get("target"):
        return None
    primary = ctx.get("primary")
    model = "PE" if primary == "PE" else ("PB" if primary == "PB" else None)
    if model is None:
        return None

    rt, bps = ctx["rt"], ctx["bps"]
    val_db = valuate(ctx["mode"], ctx["stage"], ctx["latest"], ctx["hist5"],
                     ctx["b_avg"], bps, rt.get("price"), rt.get("pe"), rt.get("pb"),
                     ctx["rf"], ctx["ind_label"], dy=ctx["dy"], debubble=True)
    val_db["bps"] = bps
    db_cfg = P.get("debubble", {})
    if not val_db.get("target"):
        return {"can": True, "applicable": False,
                "reason": "去泡沫样本不足或倍数失效，无法二次估值",
                "years": float(db_cfg.get("years", 3)),
                "cut_top": float(db_cfg.get("cut_top", 0.9))}

    unit = val.get("eps_ttm") if model == "PE" else bps
    ch_db = val_db.get("pe_ch") if model == "PE" else val_db.get("pb_ch")
    keys = ("p20", "p50", "p80") if model == "PE" else ("b20", "b50", "b80")
    band_db, px_db = _band_and_px(ch_db or {}, unit, keys)

    e_db, _prob, _rs = calc_expected_return(rt.get("price"), val_db, ctx["dy"], ctx["state"])
    buy_db = val_db["target"] * (1 - ctx["mos"])
    gate, trend = ctx["gate"], ctx["trend"]
    verdict_db = judge(ctx["g_"], ctx["stage"], trend.get("state"), gate["risk_level"],
                       len(gate["soft"]), rt.get("price"), val_db.get("fair_high"),
                       val_db.get("fair_low"), buy_db, e_db, val_db["r"],
                       invalid=val_db.get("invalid"))
    return {
        "can": True, "applicable": True,
        "years": float(db_cfg.get("years", 3)),
        "cut_top": float(db_cfg.get("cut_top", 0.9)),
        "n": (ch_db or {}).get("n"),
        "n_raw": (ch_db or {}).get("n_raw"),
        "removed": (ch_db or {}).get("removed"),
        "cut": (ch_db or {}).get("cut"),
        "band": band_db,
        "px": px_db,
        "fair_multiple": val_db.get("fair_pe") if model == "PE" else val_db.get("fair_pb"),
        "target": val_db.get("target"),
        "fair_low": val_db.get("fair_low"),
        "fair_high": val_db.get("fair_high"),
        "buy": buy_db,
        "e_return": e_db,
        "verdict": verdict_db,
        "delta": (val_db["target"] / val["target"] - 1),
    }

def run(code: str, verbose: bool = False) -> dict[str, Any]:
    log = (print if verbose else (lambda *a, **k: None))

    rt = ds.quote(code)
    if not rt:
        return {"code": code, "error": "行情获取失败"}
    log(f"  {rt['name']} 价 {rt['price']} PE {rt['pe']} PB {rt['pb']}")

    periods = ds.f10_periods(code, 26)
    time.sleep(P.get("http", {}).get("throttle", 0.3))
    annuals = sorted([p for p in periods if p.get("REPORT_TYPE") == "年报"],
                     key=lambda x: x["REPORT_DATE"], reverse=True)
    latest: dict[str, Any] = dict(annuals[0]) if annuals else (dict(periods[0]) if periods else {})
    latest["_period"] = (latest.get("REPORT_DATE") or "")[:10]
    latest["_snapshot_period"] = (periods[0].get("REPORT_DATE") or "")[:10] if periods else None
    latest["_annual_rev"] = [p.get("TOTALOPERATEREVE") for p in annuals[:3]]

    if periods:
        p0 = periods[0]
        v1, v2 = p0.get("TOTALOPERATEREVETZ"), p0.get("PARENTNETPROFITTZ")
        latest["_rev_yoy_now"] = v1 / 100 if isinstance(v1, (int, float)) else None
        latest["_np_yoy_now"] = v2 / 100 if isinstance(v2, (int, float)) else None
        prev_np = periods[1].get("PARENTNETPROFIT") if len(periods) > 1 else None
        if isinstance(prev_np, (int, float)) and prev_np <= 0:
            latest["_np_yoy_note"] = "上期亏损，同比无意义"
            latest["_np_yoy_now"] = None
            latest["_np_turn"] = ("由亏转盈" if (p0.get("PARENTNETPROFIT") or 0) > 0 else "持续亏损")
        elif isinstance(v2, (int, float)) and abs(v2) > 500:
            latest["_np_yoy_note"] = f"基期过小，同比 {v2:+.0f}% 失真"
            latest["_np_yoy_now"] = None
            latest["_np_abnormal_yoy"] = v2 / 100

    latest["_np_down_years"] = sum(
        1 for a in annuals[:3]
        if isinstance(a.get("PARENTNETPROFITTZ"), (int, float)) and a["PARENTNETPROFITTZ"] < 0)
    latest["_np_crashes"] = profit_crashes(annuals)
    latest["_quarterly"] = quarterly_profile(periods)
    latest["_q_yoy"] = quarter_yoy(periods)
    latest["_gross_margin_std"] = gross_margin_std(annuals)

    if len(annuals) >= 4:
        latest["_rev_cagr"] = cagr(annuals[3].get("TOTALOPERATEREVE"),
                                   annuals[0].get("TOTALOPERATEREVE"), 3)
        latest["_np_cagr"] = cagr(annuals[3].get("PARENTNETPROFIT"),
                                  annuals[0].get("PARENTNETPROFIT"), 3)
        gs = [g / 100 for g in (annuals[i].get("PARENTNETPROFITTZ") for i in range(min(3, len(annuals))))
              if isinstance(g, (int, float))]
        latest["_growth_std"] = st.pstdev(gs) if len(gs) >= 2 else None
    roes = [a.get("ROEJQ") for a in annuals if isinstance(a.get("ROEJQ"), (int, float))]
    if roes:
        latest["_roe_median"] = st.median(roes) / 100
        latest["_roe_latest"] = roes[0] / 100

    divs = ds.dividends(code)
    time.sleep(P.get("http", {}).get("throttle", 0.3))
    b_avg, div_used, dps_latest = _payout(annuals, divs)
    latest["_payout"] = b_avg

    bs, bs_p = ds.balance_sheet(code)
    cf, cf_p = ds.cash_flow(code)
    pl, pl_p = ds.profit_statement(code)
    gw = first_value(bs, ["商誉"]) or 0.0
    equity = first_value(bs, ["归属于母公司股东权益合计", "归属于母公司所有者权益合计", "股东权益合计"])
    cash = first_value(bs, ["货币资金"])
    latest["_cash"] = cash
    latest["_int_debt"] = calc_int_debt(bs)
    latest["_equity"] = equity
    latest["_fin_exp"] = first_value(pl, ["财务费用"])
    goodwill_ratio = (gw / equity) if (equity and equity > 0) else None
    latest["_neg_cf_years"] = neg_cf_years(cf, cf_p)
    latest["_ocf_np_5y"], latest["_ocf_yoy"], latest["_np_yoy_annual"] = _ocf_quality(
        cf, cf_p, pl, pl_p)

    capex = first_value(cf, ["购建固定资产、无形资产和其他长期资产支付的现金"])
    dep = first_value(cf, ["固定资产折旧、油气资产折耗、生产性生物资产折旧", "固定资产折旧"])
    latest["_capex_dep"] = (capex / dep) if (capex and dep) else None
    latest["_ar_inv"] = ar_inventory_growth(bs, bs_p, pl, pl_p)

    latest["_ebitda"] = ev_ebitda.ebitda_ttm(cf, cf_p, pl, pl_p)
    latest["_net_debt"] = ev_ebitda.net_debt(bs)
    latest["_capital_intensity"] = ev_ebitda.capital_intensity(cf, cf_p, pl, pl_p, bs)
    mv, px = rt.get("mktcap_yi"), rt.get("price")
    latest["_shares"] = (mv * 1e8 / px) if (mv and px) else None

    peers_codes, ind_label = peers_of(code)
    peers: list[dict[str, Any]] = []
    if peers_codes:
        rd = latest.get("REPORT_DATE", "")[:10]
        peers = ds.f10_batch([c for c in peers_codes if c != code][:60], rd)
    log(f"  行业 {ind_label}，同业样本 {len(peers)}")

    hist = ds.valuation_history(code)
    time.sleep(P.get("http", {}).get("throttle", 0.3))
    cutoff = (datetime.now() - timedelta(days=365 * HIST_YEARS)).strftime("%Y-%m-%d")
    hist5 = [h for h in hist if (h.get("TRADE_DATE") or "")[:10] >= cutoff]

    rf, rf_src, rf_degraded = ds.rf_10y()
    idx_pct, idx_close, idx_degraded = ds.hs300_percentile()
    state = market_state(idx_pct)
    pledge_row = ds.pledge(code)
    latest["_unlock"] = unlock_pressure(ds.lift_stage(code))
    latest["_pledge"] = pledge_pressure(
        ds.holder_pledge(code),
        (pledge_row or {}).get("PLEDGE_RATIO"),
        ds.controller(code),
    )
    latest["_mktcap_yi"] = rt.get("mktcap_yi")

    mode, zero_pe = classify_mode(ind_label, latest)
    trend = trend_inflection(annuals)
    trend["latest_np_yoy"] = latest.get("_np_yoy_now")
    trend["latest_rev_yoy"] = latest.get("_rev_yoy_now")
    trend["rebound"] = (latest.get("_np_yoy_now") or 0) > P.get("trend", {}).get("rebound_yoy", 0.02)
    l_np = latest.get("_np_yoy_now")
    lag_threshold = P.get("trend", {}).get("lag_yoy", -0.30)
    if trend.get("state") == "stable" and l_np is not None and l_np <= lag_threshold:
        trend.update({"state": "inflection", "basis": "最新一期",
                      "lag_warning": f"年报口径仍稳定（长期 {trend.get('L'):+.1%}／"
                                     f"短期 {trend.get('S'):+.1%}），但最新一期归母同比 "
                                     f"{l_np:+.1%}——拐点刚出现，年报尚未反映",
                      "note": f"年报口径仍稳定（长期 {trend.get('L'):+.1%}／短期 "
                              f"{trend.get('S'):+.1%}），但最新一期归母同比 {l_np:+.1%}"
                              f"——拐点刚出现，年报尚未反映"})
    latest["_trend"] = trend

    pc_state, pc_why = profit_cash_check(latest, mode)
    latest["_pc_state"], latest["_pc_why"] = pc_state, pc_why
    stage, stage_why, substage = judge_lifecycle(latest, mode)

    gate = screen(rt["name"], latest, pledge_row, goodwill_ratio)

    base = {"code": code, "name": rt["name"], "price": rt["price"],
            "pe": rt["pe"], "pb": rt["pb"], "industry": ind_label,
            "as_of": latest.get("_snapshot_period"),
            "gate": gate, "trend": trend,
            "profile": {"mode": mode, "zero_pe": zero_pe, "stage": stage,
                        "stage_why": stage_why, "substage": substage},
            "source": {"rf": rf, "rf_src": rf_src, "rf_degraded": rf_degraded,
                       "idx_pct": idx_pct, "idx_close": idx_close,
                       "idx_degraded": idx_degraded}}

    if any((ind_label or "").startswith(p) for p in ("J68",)):
        base.update({"avoid": True,
                     "reason": "寿险/健康险为主：PE 与 PB 均受精算假设扭曲，PEV/NBV 属进阶工具，"
                               "按教程建议新手回避，本系统不输出定价"})
        return base

    if not gate["passed"]:
        base.update({"rejected": True})
        return base

    dims, total, details, missing_dims, dim_detail = six_dim_score(
        latest, peers, goodwill_ratio, mode)
    g_, mos = grade(total)

    bps = latest.get("BPS")
    if not bps and equity and latest.get("TOTAL_SHARE"):
        bps = equity / latest["TOTAL_SHARE"]
    dy = (dps_latest / rt["price"]) if (dps_latest and rt["price"]) else None
    val = valuate(mode, stage, latest, hist5, b_avg, bps, rt["price"],
                  rt.get("pe"), rt.get("pb"), rf, ind_label, dy=dy)
    val["bps"] = bps

    e, prob, rs = calc_expected_return(rt["price"], val, dy, state)
    buy = (val["target"] * (1 - mos)) if val.get("target") else None
    val["buy"] = buy
    verdict = judge(g_, stage, trend.get("state"), gate["risk_level"], len(gate["soft"]),
                    rt["price"], val.get("fair_high"), val.get("fair_low"), buy, e, val["r"],
                    invalid=val.get("invalid"))
    ff, ff_notes = five_forces_analyze(latest, peers)

    base["channel"] = _build_channel(val, rt, bps, hist5)
    base["_ctx"] = {
        "mode": mode, "stage": stage, "latest": latest, "hist5": hist5,
        "b_avg": b_avg, "bps": bps, "rt": rt, "rf": rf, "ind_label": ind_label,
        "dy": dy, "state": state, "g_": g_, "mos": mos, "trend": trend, "gate": gate,
        "primary": val.get("primary"),
    }

    base.update({
        "score": {"total": total, "grade": g_, "dims": dims, "details": details,
                  "dim_detail": dim_detail,
                  "dupont": None, "peers": len(peers), "missing_dims": missing_dims},
        "profile": {"mode": mode, "zero_pe": zero_pe, "stage": stage,
                    "stage_why": stage_why, "substage": substage,
                    "five_forces": ff, "five_notes": ff_notes},
        "valuation": val,
        "aux": {"dividend_yield": dy, "pe_percentile": val.get("cur_pct"),
                "pe_vs_median": ((rt["pe"] / val["p50"] - 1)
                                 if (rt.get("pe") and val.get("p50")) else None),
                "dividends": div_used},
        "decision": {"E": e, "prob": prob, "R": rs, "market_state": state,
                     "idx_pct": idx_pct, "mos": mos, "buy": buy, "verdict": verdict,
                     "position": position_suggestion(g_, e, val["r"])},
    })
    return base
