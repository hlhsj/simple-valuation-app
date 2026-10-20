from __future__ import annotations

from typing import Any

from ..config import params

P = params()

def bank_asset_penalty(fin: dict[str, Any]) -> tuple[float, str]:
    cfg = P.get("bank", {})
    npl, prov = fin.get("NONPERLOAN"), fin.get("BLDKBBL")
    p, bits = 0.0, []
    if npl is not None and npl > cfg.get("npl_base", 1.0):
        d = min(0.15, (npl - cfg.get("npl_base", 1.0)) * cfg.get("npl_penalty_per_pp", 0.15))
        p += d
        bits.append(f"不良率 {npl:.2f}%（−{d:.1%}）")
    if prov is not None and prov < cfg.get("prov_base", 250):
        d = min(0.15, (cfg.get("prov_base", 250) - prov) / 100.0
                * cfg.get("prov_penalty_per_100pp", 0.07))
        p += d
        bits.append(f"拨备 {prov:.0f}%（−{d:.1%}）")
    p = min(p, cfg.get("max_penalty", 0.25))
    return p, "、".join(bits)

def model_validity(target: float | None, trend_state: str | None) -> str | None:
    if target is not None and target <= 0:
        return (f"主模型算出负价（{target:.2f} 元），说明该企业的盈利/净资产已无法"
                f"支撑戈登模型的假设，不出区间与买点")
    if trend_state == "collapse":
        return "由盈转亏，PE/PB 模型同时失效，不出区间与买点"
    return None
