from __future__ import annotations

from ..config import params

P = params()

def rim_value(r: float, g: float, roe: float | None, bps: float | None,
              pb_median: float | None = None,
              roe_now: float | None = None) -> dict[str, object]:
    if not bps or not roe or roe <= 0:
        return {"applicable": False, "reason": "ROE ≤ 0 或 BPS 缺失"}
    if r - g <= 0.005:
        return {"applicable": False, "reason": "r − g ≤ 0.5pp，分母失效"}
    if roe_now is not None and roe_now <= 0:
        return {"applicable": False,
                "reason": f"当期 ROE {roe_now:.1f}% 为负（亏损），历史中位 {roe:.1%} 不可外推"}

    pb_rim = 1 + (roe - r) / (r - g)
    if pb_rim <= 0:
        return {"applicable": False,
                "reason": f"理论 PB 为负（{pb_rim:.2f}）——ROE {roe:.1%} 低于要求回报 "
                          f"{r:.1%}，按剩余收益模型看是在毁灭价值"}

    out: dict[str, object] = {"applicable": True, "pb": pb_rim,
                              "value": pb_rim * bps, "roe": roe,
                              "pe_implied": pb_rim / roe}
    if pb_median and pb_median > 0:
        pb_mix = (pb_rim * pb_median) ** 0.5
        out.update({"pb_mix": pb_mix, "value_mix": pb_mix * bps,
                    "pb_median": pb_median, "pe_mix": pb_mix / roe})
    return out
