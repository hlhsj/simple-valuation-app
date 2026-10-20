from __future__ import annotations

from ..config import params

P = params()

def suggestion(grade_: str, e: float | None, r: float,
               industry_weight: float = 0.0) -> dict[str, object]:
    cfg = P.get("position", {})
    single = cfg.get("single_max", 0.20)
    ind_max = cfg.get("industry_max", 0.40)
    c_max = cfg.get("c_grade_max", 0.05)

    cap = single
    if grade_ == "C":
        cap = min(cap, c_max)
    if grade_ == "D":
        cap = 0.0
    room = max(0.0, ind_max - industry_weight)
    cap = min(cap, room)

    if e is None:
        frac = 0.0
    else:
        excess = max(0.0, e - r)
        frac = min(1.0, excess / 0.15)

    total = round(cap * frac, 4)
    return {"cap": cap, "confidence_frac": round(frac, 3),
            "first_tranche": round(total / 3, 4) if total else 0.0,
            "note": "首笔 = 目标仓位 / 3（分批建仓）" if total else "不满足建仓条件"}
