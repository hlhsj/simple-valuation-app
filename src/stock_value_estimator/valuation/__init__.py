from __future__ import annotations

from typing import Any

from ..config import params
from . import (channel, ev_ebitda, model_router, normalized, pb_model,
              pe_model, rim_model, special)

P = params()

def required_return(mode: str, stage: str, rf: float) -> tuple[float, float]:
    erp = P.get("erp", {}).get(mode, 0.085)
    if stage == "成长期":
        erp += P.get("erp_growth_extra", 0.015)
    return rf + erp, erp

def perpetual_growth(stage: str, latest: dict[str, Any], r: float) -> tuple[float, str]:
    if stage == "成长期":
        base = latest.get("_rev_cagr") or 0.05
        g = min(max(base * P.get("g_growth_ratio", 0.5), 0.0),
                P.get("g_cap", 0.05), r - P.get("g_r_spread", 0.02))
        return g, f"成长期：营收 CAGR×{P.get('g_growth_ratio', 0.5):.1f}，上限 5% 且 ≤ r−2pp"
    if stage == "衰退期":
        return P.get("g_decline", -0.01), "衰退期：取 −1%"

    pc_state = latest.get("_pc_state")
    pc_why = latest.get("_pc_why")
    rev_c = latest.get("_rev_cagr")
    if pc_state == "zero":
        return 0.0, f"成熟期但利润收缩已获现金流确认（{pc_why}），永续增长按 0 处理"
    if pc_state == "soft":
        g = P.get("g_mature", 0.025) * P.get("g_soft_ratio", 0.5)
        return g, f"成熟期，{pc_why}，永续增长按 {g:.2%}（常规对折）"
    if rev_c is not None and rev_c < 0:
        return P.get("g_mature_saturated", -0.005), f"成熟期但营收负增长（{rev_c:.1%}），取 −0.5%"
    return P.get("g_mature", 0.025), "成熟期：取 2.5%"

def effective_b(b: float, r: float, g: float,
                roe: float | None,
                dy: float | None = None) -> tuple[float, str]:
    cfg = P.get("pe_low_b", {})
    thr = float(cfg.get("b_threshold", 0.30))
    dy_cap = float(cfg.get("dividend_yield_cap", 0.015))
    disc = float(cfg.get("rim_discount", 0.7))
    if b >= thr or not roe or roe <= r or (r - g) <= 0.005:
        return b, ""
    if dy is not None and dy >= dy_cap:
        return b, ""
    pe_rim = (1 + (roe - r) / (r - g)) / roe
    b_eff = min(1.0, pe_rim * disc * (r - g))
    if b_eff <= b:
        return b, ""
    return b_eff, (f"分红率仅 {b:.1%}（利润主要留存再投资），戈登口径按 "
                   f"{b_eff:.1%} 计——RIM 隐含 PE {pe_rim:.1f}× 打 {disc:.0%} 作为下限")

def _caveats(b: float, r: float, g: float, roe_chk: float | None,
             b_used: float | None = None,
             dy: float | None = None) -> list[str]:
    out = []
    if g <= 0:
        out.append("g ≤ 0 时戈登 PE 退化为 b/r，对低分红企业会给出机械偏低的倍数："
                   "结论方向可靠，幅度不宜精读")
    cfg = P.get("pe_low_b", {})
    thr = float(cfg.get("b_threshold", 0.30))
    dy_cap = float(cfg.get("dividend_yield_cap", 0.015))
    corrected = b_used is not None and b_used > b + 0.001
    if corrected:
        out.append(f"当期分红率仅 {b:.0%}，已按「留存利润以 ROE {roe_chk:.1%} "
                   f"再投资」口径修正为 {b_used:.0%}；若实际再投资回报不及 ROE，"
                   f"合理价应下调")
    elif (b < thr and roe_chk and roe_chk > r
          and (dy is None or dy < dy_cap)):
        out.append(f"分红率仅 {b:.0%}、ROE {roe_chk:.1%} 高于要求回报 {r:.1%}——"
                   f"戈登模型隐含「留存利润只赚 g」，会系统性低估这类把利润留在"
                   f"体内再投资的企业；该结论应视为估值下限，而非合理中枢")
    return out

def evaluate(mode: str, stage: str, latest: dict[str, Any],
             hist: list[dict[str, Any]], b: float,
             bps: float | None, price: float | None, pe_now: float | None,
             pb_now: float | None, rf: float,
             industry_label: str | None = None,
             dy: float | None = None) -> dict[str, Any]:
    r, erp = required_return(mode, stage, rf)
    g, g_note = perpetual_growth(stage, latest, r)

    primary, auxiliary, route_reason = model_router.route(mode, stage, industry_label)

    degraded = False
    eps_ttm = (price / pe_now) if pe_now else None
    if primary == "PE":
        degrade, why = ev_ebitda.should_degrade(primary, pe_now, eps_ttm,
                                                latest.get("_capital_intensity"))
        if degrade:
            primary = "EV/EBITDA"
            route_reason = why + " → 主模型降级为 EV/EBITDA"
            degraded = True

    pe_ch = channel.pe_channel(hist)
    pb_ch = channel.pb_channel(hist)
    cur_pct = channel.current_percentile(hist, "PE_TTM", pe_now)

    roe_med = latest.get("_roe_median")
    if roe_med is None:
        roe_med = (latest.get("ROEJQ") or 0) / 100
    if mode == "资本型":
        roe_now = latest.get("_roe_latest") or roe_med
        roe_med = min(roe_med, roe_now)
    g_sus = roe_med * (1 - b)

    res: dict[str, Any] = {
        "r": r, "rf": rf, "erp": erp, "g": g, "g_note": g_note,
        "b": b, "roe": roe_med, "primary": primary, "auxiliary": auxiliary,
        "route_reason": route_reason,
        "pe_now": pe_now, "pb_now": pb_now, "cur_pct": cur_pct,
        "pb_median": pb_ch["b50"],
        "p20": pe_ch["p20"], "p50": pe_ch["p50"], "p80": pe_ch["p80"],
        "b20": pb_ch["b20"], "b50": pb_ch["b50"], "b80": pb_ch["b80"],
        "g_sus": g_sus, "consistent": g <= g_sus + 0.005,
    }

    if primary == "PB":
        raw, fair, note = pb_model.fair_pb(roe_med, r, g, hist)
        penalty, pbits = (special.bank_asset_penalty(latest) if mode == "资本型" else (0.0, ""))
        if fair and penalty:
            fair = fair * (1 - penalty)
            note += f"，资产质量折价 {penalty:.1%}（{pbits}）"
        target = fair * bps if (fair and bps) else None
        norm_eps = normalized.normalized_eps(roe_med, bps)
        res.update({"fair_pb_gordon": raw, "fair_pb": fair, "target": target,
                    "anchor_note": note, "asset_penalty": penalty,
                    "norm_eps": norm_eps, "eps_ttm": (price / pe_now) if pe_now else None,
                    "norm_pe": normalized.normalized_pe(norm_eps, price),
                    "roe_used": roe_med})
    elif primary == "PE":
        _roe_now = latest.get("_roe_latest")
        _roe_for_b = max(roe_med, _roe_now) if _roe_now else roe_med
        b_eff, b_note = effective_b(b, r, g, _roe_for_b, dy=dy)
        raw, fair, note = pe_model.fair_pe(b_eff, r, g, hist)
        target = fair * eps_ttm if (fair and eps_ttm) else None
        if b_note:
            note = f"{b_note}；{note}"
        res.update({"fair_pe_gordon": raw, "fair_pe": fair, "target": target,
                    "anchor_note": note, "eps_ttm": eps_ttm,
                    "b_raw": round(b, 4), "b_used": round(b_eff, 4)})
    elif primary == "EV/EBITDA":
        g_ev = min(latest.get("_rev_cagr") or 0.05, P.get("g_cap", 0.05))
        eb = latest.get("_ebitda") or {}
        eb_val = eb.get("ttm") if eb.get("ok") else None
        ev_res = ev_ebitda.value(eb_val, latest.get("_net_debt"),
                                 latest.get("_shares"), r, g_ev, industry_label)
        res.update({"ev_ebitda": ev_res, "g_ev": g_ev,
                    "eps_ttm": eps_ttm})
        if ev_res.get("applicable"):
            res.update({"target": ev_res["target"],
                        "anchor_note": (f"EV/EBITDA 降级模型：{ev_res['mult_note']}；"
                                        f"EBITDA(TTM) {ev_res['ebitda']/1e8:.0f} 亿 − "
                                        f"净债务 {(ev_res['net_debt'] or 0)/1e8:.0f} 亿 → "
                                        f"股权 {ev_res['equity']/1e8:.0f} 亿 / "
                                        f"{ev_res['shares']/1e8:.1f} 亿股")})
        else:
            res.update({"target": None,
                        "anchor_note": f"EV/EBITDA 不适用：{ev_res.get('reason')}"})
    else:
        res.update({"fair_pe": None, "fair_pb": None, "target": None,
                    "anchor_note": route_reason})

    _cav = _caveats(b, r, g,
                    latest.get("_roe_latest") or (latest.get("ROEJQ") or 0) / 100,
                    res.get("b_used"), dy)
    if degraded:
        _cav.append("EV/EBITDA 为降级模型：行业倍数系人工标定（非计算得出），"
                    "结论方向可靠、幅度不宜精读")
    _dev_thr = float(P.get("pe_low_b", {}).get("deviation_warn", 2.0))
    _tgt, _px = res.get("target"), price
    if _tgt and _px and _tgt > 0 and _px > 0:
        _ratio = max(_px / _tgt, _tgt / _px)
        if _ratio > _dev_thr:
            _cav.append(f"合理价 {_tgt:.2f} 元与现价 {_px:.2f} 元相差 {_ratio:.1f} 倍，"
                        f"已超过程序化模型的解释范围——该股定价主要由业绩预期与资金面"
                        f"驱动，本模型不适用于判断其贵贱")
    res["caveat"] = "；".join(_cav) or None

    invalid = special.model_validity(res.get("target"),
                                     (latest.get("_trend") or {}).get("state"))
    if invalid:
        res.update({"invalid": invalid, "target": None,
                    "fair_low": None, "fair_high": None, "buy": None})
    else:
        lo, hi = P.get("fair_band", [0.90, 1.10])
        res.update({"invalid": None,
                    "fair_low": res["target"] * lo if res.get("target") else None,
                    "fair_high": res["target"] * hi if res.get("target") else None})

    res["rim"] = rim_model.rim_value(r, g, roe_med, bps, res.get("pb_median"),
                                     latest.get("ROEJQ"))
    return res

__all__ = [
    "channel", "ev_ebitda", "model_router", "normalized", "pb_model", "pe_model",
    "rim_model", "special",
    "evaluate", "required_return", "perpetual_growth",
]
