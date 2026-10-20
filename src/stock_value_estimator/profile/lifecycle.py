from __future__ import annotations

import statistics as st
from typing import Any

from ..config import params

P = params()

def trend_inflection(annuals: list[dict[str, Any]]) -> dict[str, Any]:
    def series(key: str) -> list[tuple[str, float]]:
        out = []
        for p in annuals:
            v = p.get(key)
            if isinstance(v, (int, float)):
                out.append((p["REPORT_DATE"][:4], v))
        return out

    rev, npf = series("TOTALOPERATEREVE"), series("PARENTNETPROFIT")

    def cagr(seq: list[tuple[str, float]], n: int) -> float | None:
        if len(seq) <= n:
            return None
        a, b = seq[n][1], seq[0][1]
        if a <= 0 or b <= 0:
            return None
        return (b / a) ** (1 / n) - 1

    l5r, s2r = cagr(rev, 5), cagr(rev, 2)
    l5n, s2n = cagr(npf, 5), cagr(npf, 2)

    gm = [p.get("XSMLL") for p in annuals[:6] if isinstance(p.get("XSMLL"), (int, float))]
    gm_std = (st.pstdev(gm) / 100) if len(gm) >= 4 else None

    out: dict[str, Any] = {"l_rev": l5r, "s_rev": s2r, "l_np": l5n, "s_np": s2n,
                           "gm_std": gm_std, "years": len(annuals)}

    k = min(4, len(npf) - 1)
    if len(npf) >= 3 and npf[0][1] < 0 and npf[k][1] > 0:
        out.update({"state": "collapse", "basis": "归母",
                    "note": f"{npf[k][0]} 年归母 {npf[k][1]/1e8:.0f} 亿 → "
                            f"{npf[0][0]} 年 {npf[0][1]/1e8:.0f} 亿，由盈转亏"})
        return out

    L = max([x for x in (l5r, l5n) if x is not None], default=None)
    S = min([x for x in (s2r, s2n) if x is not None], default=None)
    if L is None or S is None:
        out.update({"state": "unknown", "basis": None,
                    "note": f"年报仅 {len(annuals)} 期，不足 6 期，无法判定长期趋势"})
        return out

    t = P.get("trend", {})
    out["L"], out["S"] = L, S
    who = "营收" if (s2r is not None and s2n is not None and s2r <= s2n) else "归母"
    if L >= t.get("long_min", 0.03) and S <= t.get("short_max", -0.05):
        out.update({"state": "inflection", "basis": who,
                    "note": f"5 年 CAGR 最优 {L:+.1%}，近 2 年最差 {S:+.1%}（{who}）——"
                            f"长斜率仍向上、短斜率已掉头"})
    elif (L >= t.get("long_min", 0.03) and S < L * t.get("decel_ratio", 0.4)
          and (L - S) >= t.get("decel_gap", 0.10)):
        out.update({"state": "decelerate", "basis": who,
                    "note": f"5 年 CAGR 最优 {L:+.1%}，近 2 年最差 {S:+.1%}（{who}），"
                            f"增速只剩不到四成但未转负"})
    elif L < t.get("long_min", 0.03) and S <= t.get("short_max", -0.05):
        out.update({"state": "stagnant", "basis": who,
                    "note": f"长期{'已负增长' if L < 0 else '本就停滞'}（5 年 CAGR 最优"
                            f"{'' if L < 0 else '仅'} {L:+.1%}），近 2 年最差 {S:+.1%}（{who}）"
                            f"——不是高增长掉头，而是存量收缩"})
    else:
        out.update({"state": "stable", "basis": None,
                    "note": f"长期 {L:+.1%} / 短期 {S:+.1%}，趋势未见背离"})
    return out

def profit_cash_check(latest: dict[str, Any], mode: str) -> tuple[str, str]:
    l_np = latest.get("_np_yoy_now")
    down = latest.get("_np_down_years") or 0
    ocf_yoy = latest.get("_ocf_yoy")
    ocf_np = latest.get("_ocf_np_5y")

    rebounded = l_np is not None and l_np >= P.get("profit_rebound", 0.10)
    profit_down = ((l_np is not None and l_np <= -0.10)
                   or (down >= 2 and not rebounded))
    if not profit_down:
        why = (f"最新一期归母同比 {l_np:+.1%}，未达 −10% 的下滑判定线" if l_np is not None
               else "利润未出现显著下滑")
        if rebounded and down >= 2:
            why = (f"近三年有 {down} 年利润负增长，但最新一期归母同比 {l_np:+.1%} "
                   f"已明显回升——收缩期可能已过去，不按收缩处理")
        return "normal", why

    if l_np is not None and l_np <= -0.10:
        head = f"最新一期归母同比 {l_np:+.1%}"
    else:
        head = f"近三年有 {down} 年利润负增长"
        if l_np is not None:
            head += f"（最新一期 {l_np:+.1%} 尚未明显回升）"
    if mode == "资本型":
        return "zero", f"{head}，金融机构不适用现金流校验，按利润判"

    cash_bad = (ocf_yoy is not None and ocf_yoy < P.get("ocf_yoy_bad", -0.20)) or (
        ocf_np is None or ocf_np < P.get("cash_quality_min", 0.80))
    if cash_bad:
        bits = []
        if ocf_yoy is not None and ocf_yoy < P.get("ocf_yoy_bad", -0.20):
            bits.append(f"年报经营现金流同比 {ocf_yoy:+.1%}")
        if ocf_np is None:
            bits.append("5 年累计现金含量不可得")
        elif ocf_np < P.get("cash_quality_min", 0.80):
            bits.append(f"5 年累计现金含量仅 {ocf_np:.2f}（利润未转化为现金）")
        return "zero", f"{head}，且 " + "、".join(bits) + "——现金流未提供支撑"
    return "soft", (f"{head}，但 5 年累计现金含量 {ocf_np:.2f}≥0.80、"
                    f"年报现金流同比 {ocf_yoy:+.1%}，未获现金流确认，暂按对折处理")

def lifecycle(latest: dict[str, Any], mode: str | None = None) -> tuple[str, str, str | None]:
    rev_c, np_c = latest.get("_rev_cagr"), latest.get("_np_cagr")
    div_payout, capex_ratio = latest.get("_payout"), latest.get("_capex_dep")
    npf = latest.get("PARENTNETPROFIT") or 0
    roe = latest.get("ROEJQ") or 0
    l_rev = latest.get("_rev_yoy_now")
    down = latest.get("_np_down_years") or 0
    pc_state, pc_why = profit_cash_check(latest, mode)

    if rev_c is None:
        return "成熟期", "营收 CAGR 不可得，默认按成熟期处理（置信度 0.6）", None
    if npf < 0 and rev_c < 0:
        return "衰退期", f"营收 CAGR {rev_c:.1%} 为负且亏损", None
    if rev_c <= -0.10:
        return "衰退期", f"营收 CAGR {rev_c:.1%} ≤ −10%，属结构性萎缩（非周期性低谷）", None

    profit_ok = (np_c is not None and np_c >= 0.15) and pc_state != "zero"
    if rev_c >= 0.20 and profit_ok:
        note = f"营收 CAGR {rev_c:.1%} ≥20%、归母 CAGR {(np_c or 0):.1%} ≥15%"
        if capex_ratio and capex_ratio >= 0.1:
            note += f"，资本开支/折旧 {capex_ratio:.2f}"
        return "成长期", note, None

    if rev_c >= 0.20 and not profit_ok:
        seg = []
        if np_c is not None and np_c < 0.15:
            seg.append(f"归母 CAGR 仅 {np_c:.1%}")
        if pc_state == "zero":
            seg.append(pc_why)
        if down >= 1:
            seg.append(f"近三年有 {down} 年利润负增长")
        return "成熟期", "营收 CAGR 仍高，但" + "、".join(seg) + "——增收不增利，成长已失速", \
            "成长失速"

    if rev_c >= 0:
        note = f"营收 CAGR {rev_c:.1%} 落在 0–20% 成熟区间，分红率 {(div_payout or 0):.0%}"
        if pc_state != "normal":
            note += f"；{pc_why}"
        sub = {"zero": "利润收缩", "soft": "利润待观察"}.get(pc_state)
        return "成熟期", note, sub

    if (div_payout or 0) >= 0.30 and npf > 0:
        tag = "营收回升" if (l_rev is not None and l_rev > 0.02) else "营收收缩"
        return ("成熟期",
                f"营收 CAGR {rev_c:.1%} 为负但分红率 {(div_payout or 0):.0%}≥30% 且仍盈利"
                + (f"；最新一期营收同比 {l_rev:+.1%}，已在回升" if tag == "营收回升" else ""),
                tag)
    if npf < 0 or roe < 5:
        return "衰退期", f"营收 CAGR {rev_c:.1%} 为负且 ROE {roe:.1f}%/盈利恶化", None
    return "成熟期", f"营收 CAGR {rev_c:.1%} 为负但盈利尚可，按成熟期后期处理", "营收收缩"
