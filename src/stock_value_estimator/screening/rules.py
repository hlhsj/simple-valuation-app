from __future__ import annotations

from typing import Any

from ..config import params

P = params()

def screen(name: str, latest: dict[str, Any], pledge_row: dict[str, Any] | None,
           goodwill_ratio: float | None,
           manual_flags: list[str] | None = None) -> dict[str, Any]:
    hard: list[str] = []
    soft: list[str] = []

    pledge_info = latest.get("_pledge") or {}
    pledge_cfg = P.get("pledge", {})

    if "ST" in (name or "").upper():
        hard.append(f"H1 ST/*ST（{name}）")

    c_hold = pledge_info.get("controller_holder_ratio")
    h3_thr = pledge_cfg.get("holder_ratio_hard", 30.0)
    if c_hold is not None and c_hold >= h3_thr:
        nm = pledge_info.get("controller_holder_name") or "控股股东"
        pw = pledge_info.get("controller_holder_pledged_wan")
        hw = pledge_info.get("controller_holder_hold_wan")
        detail = ""
        if isinstance(pw, (int, float)) and isinstance(hw, (int, float)):
            detail = f"——{nm} 已质押 {pw:.0f} 万股 / 持股 {hw:.0f} 万股"
        else:
            detail = f"——{nm}"
        hard.append(f"H3 控股股东质押占其持股 {c_hold:.1f}%（>{h3_thr:.0f}%）{detail}")

    crashes = latest.get("_np_crashes") or []
    cyc = (latest.get("_trend") or {}).get("gm_std") or 0
    cyc_exempt = P.get("crash", {}).get("cyclic_exempt_gm_std", 0.08)
    min_times = P.get("crash", {}).get("min_times", 2)
    if len(crashes) >= min_times and cyc <= cyc_exempt:
        detail = "、".join(f"{y} {c:+.0%}" for y, c in crashes[:4])
        hard.append(f"H6 利润反复暴跌：近 8 年 {len(crashes)} 次单年归母跌幅 >40%（{detail}）")

    c_ratio = pledge_info.get("controller_ratio")
    c_hard = pledge_cfg.get("controller_hard", 1.0)
    if c_ratio is not None and c_ratio >= c_hard:
        names = "、".join(pledge_info.get("controller_names") or []) or "实控人"
        hard.append(f"H7 实控股东质押：{names} 质押合计占总股本 {c_ratio:.2f}%"
                    f"（≥{c_hard:.0f}%）——实控人以股权质押融资，存在平仓与被动减持风险")

    for k in (manual_flags or []):
        hard.append(k)

    cash = latest.get("_cash")
    int_debt = latest.get("_int_debt")
    equity = latest.get("_equity")
    fin_exp = latest.get("_fin_exp")
    if cash and int_debt is not None and equity:
        if cash > int_debt * 1.5 and int_debt > equity * 0.3 and (fin_exp or 0) > 0:
            soft.append(f"S5 存贷双高：货币资金 {cash/1e8:.0f} 亿 > 有息负债 "
                        f"{int_debt/1e8:.0f} 亿 × 1.5，且财务费用 {fin_exp/1e8:.1f} 亿")

    nco = latest.get("_ocf_np_5y")
    if nco is None:
        nco = latest.get("NCO_NETPROFIT")
    if nco is not None and nco < P.get("cash_quality_soft", 0.70):
        soft.append(f"S1 5 年累计现金含量 {nco:.2f} < 0.7（利润长期未转化为现金）")

    npf, kcf = latest.get("PARENTNETPROFIT"), latest.get("KCFJCXSYJLR")
    if npf and kcf is not None and npf > 0 and kcf / npf < 0.7:
        soft.append(f"S2 扣非/归母 {kcf/npf:.2f} < 0.7")

    trend = latest.get("_trend") or {}
    tstate = trend.get("state")
    if tstate == "collapse":
        soft.append(f"S3 由盈转亏：{trend.get('note')}")
    elif tstate == "inflection":
        soft.append(f"S3 长期向上、短期掉头：{trend.get('note')}")

    if goodwill_ratio is not None and goodwill_ratio > 0.30:
        soft.append(f"S4 商誉/净资产 {goodwill_ratio:.1%} > 30%")

    cyc_threshold = P.get("trend", {}).get("cyclic_gm_std", 0.08)
    if cyc > cyc_threshold:
        extra = ""
        if len(crashes) >= min_times:
            extra = (f"；且近 8 年已有 {len(crashes)} 次单年归母跌幅 >40%，"
                     f"正是周期波动的体现（因此不适用 H6 硬否决，改为减分）")
        soft.append(f"S6 强周期特征：毛利率 σ 达 {cyc:.1%}（>{cyc_threshold:.0%}），"
                    f"业绩随商品价格大幅波动，估值必须先判断周期位置，新手难以把握{extra}")

    unlock = latest.get("_unlock") or {}
    u_worst = unlock.get("worst")
    u_cfg = P.get("unlock", {})
    ratio_soft = u_cfg.get("ratio_soft", 0.05)
    ratio_high = u_cfg.get("ratio_high", 0.10)
    if u_worst and u_worst["ratio"] >= ratio_soft:
        kind = "、".join(u_worst.get("types") or []) or "未披露类型"
        tag = "重大解禁" if u_worst["ratio"] >= ratio_high else "解禁"
        if u_worst["when"] == "future":
            when = "今日" if u_worst["days"] == 0 else f"距今 {u_worst['days']} 天"
            head = f"将于 {u_worst['date']}（{when}）解禁"
            tail = "，需提前评估抛压"
        else:
            head = f"{u_worst['date']} 已解禁（{-u_worst['days']} 天前）"
            tail = "，抛压仍在释放期"
        soft.append(f"S7 {tag}：{head}，占总股本 {u_worst['ratio']:.1%}"
                    f"（{kind}）{tail}")

    p_total = pledge_info.get("total") or 0.0
    p_soft = pledge_cfg.get("total_soft", 1.0)
    if (c_ratio is None or c_ratio < c_hard) and p_total >= p_soft:
        holders = pledge_info.get("by_holder") or []
        who = "、".join(f"{x['name']} {x['ratio']:.2f}%" for x in holders[:4])
        src = "" if pledge_info.get("trusted", True) else "（股东明细滞后，按公司整体口径）"
        soft.append(f"S8 股东质押：重要股东质押合计占总股本 {p_total:.2f}%"
                    f"（≥{p_soft:.0f}%）{src}" + (f"，其中 {who}" if who else ""))

    mv = latest.get("_mktcap_yi")
    mv_cfg = P.get("mktcap", {}).get("small_yi", 50)
    if isinstance(mv, (int, float)) and 0 < mv < mv_cfg:
        soft.append(f"S9 市值偏小：总市值 {mv:.0f} 亿元（<{mv_cfg} 亿），"
                    f"抗风险能力、流动性与信息透明度均弱于大市值公司")

    rev_yoy, np_yoy = latest.get("_rev_yoy_now"), latest.get("_np_yoy_now")
    rp = P.get("revenue_profit", {})
    if (isinstance(rev_yoy, (int, float)) and isinstance(np_yoy, (int, float))
            and rev_yoy >= rp.get("rev_min", 0.05)
            and np_yoy < rev_yoy * rp.get("np_ratio", 0.30)
            and (rev_yoy - np_yoy) >= rp.get("gap_min", 0.05)):
        soft.append(f"S10 增收不增利：最新一期营收 {rev_yoy:+.1%}，归母仅 {np_yoy:+.1%}"
                    f"（增速差 {(rev_yoy - np_yoy) * 100:.1f}pp）——营收在扩张，利润没有跟上，"
                    f"多为价格战、成本失控或低毛利业务占比上升")

    qp = latest.get("_quarterly") or {}
    if qp.get("front_loaded"):
        yrs = "、".join(qp.get("front_years", [])[:3])
        soft.append(f"S11 利润前置：Q1 贡献全年 {qp['q1_share']:.0%}、Q4 仅 {qp['q4_share']:.0%}"
                    f"（{yrs} 连续如此）——利润在年初集中释放，后三季度经营信号失真，"
                    f"按年度同比看不出来")
    elif qp.get("single_loss"):
        losses = "、".join(f"{k} {v:.1f} 亿" for k, v in qp.get("loss_quarters", [])[:2])
        soft.append(f"S11 单季亏损：{qp['year']} 年 {losses}，但全年仍盈利 "
                    f"{qp.get('fy_yi'):.1f} 亿——季度口径已经亏了，年度口径完全看不出，"
                    f"存在利润跨季调节或 Q4 集中计提的可能")

    ai = latest.get("_ar_inv") or {}
    ai_cfg = P.get("receivable_inventory", {})
    ai_gap_thr = ai_cfg.get("gap", 0.20)
    if (ai.get("applicable") and ai.get("worst")
            and (ai.get("gap") or 0) > ai_gap_thr):
        w = ai[ai["worst"]]
        is_ar = ai["worst"] == "receivable"
        subj = "应收票据及应收账款" if is_ar else "存货"
        other_key = "inventory" if is_ar else "receivable"
        other = ai.get(other_key) or {}
        extra = ""
        if other.get("usable") and (other.get("gap") or 0) > ai_gap_thr:
            other_name = "存货" if other_key == "inventory" else "应收"
            extra = (f"；同时{other_name}同比 {other['growth']:+.1%}，"
                     f"同样远超营收")
        up = ai["rev_growth"] > 0
        if is_ar:
            tail = ("收入在增长，但钱收得比收入慢——可能是放宽账期换增长，"
                    "也可能是客户结构变化，需结合应收账龄与坏账计提核实" if up else
                    "营收在下滑、应收却还在涨——多为回款能力恶化，"
                    "或前期确认的收入迟迟未兑现")
        else:
            tail = ("收入在增长，但库存涨得更快——可能是为后续订单主动备货，"
                    "也可能是渠道压货，需结合存货周转天数与订单情况核实" if up else
                    "营收在下滑、库存却还在涨——典型滞销积压，"
                    "后续大概率面临跌价计提")
        soft.append(
            f"S12 {'应收膨胀' if is_ar else '存货积压'}：{subj} {ai['year']} 年"
            f"同比 {w['growth']:+.1%}（{w['yi']:.1f} 亿元，占营收 "
            f"{w['rev_ratio']:.1%}），营收仅 {ai['rev_growth']:+.1%}"
            f"——增速差 {w['gap'] * 100:.1f}pp。{tail}{extra}")

    level = ("不通过" if hard else
             "高危" if len(soft) >= P.get("risk", {}).get("high_risk_soft", 3) else
             "关注" if soft else "正常")
    return {"passed": len(hard) == 0, "hard": hard, "soft": soft, "risk_level": level}
