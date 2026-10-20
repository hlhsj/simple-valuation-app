from __future__ import annotations

from typing import Any

from ..scoring.anchors import pct_rank

def analyze(latest: dict[str, Any], peers: list[dict[str, Any]]) -> tuple[dict, list[str]]:
    gm, gm_tb = latest.get("XSMLL"), latest.get("XSMLL_TB")
    ap = pct_rank(latest.get("PAYABLE_TDAYS"), [p.get("PAYABLE_TDAYS") for p in peers], True)
    ar = pct_rank(latest.get("YSZKZZTS"), [p.get("YSZKZZTS") for p in peers], False)
    cs, roic = latest.get("XSJXLYYSR"), latest.get("ROIC")
    nm, sell_er = latest.get("XSJLL"), latest.get("SALE_ER_PK")
    inv = latest.get("INVENTORY_TR_YOY")

    f = {
        "supplier": 5 if (gm and gm >= 30 and ap and ap > 70) else (4 if (gm and gm >= 25) else 2),
        "buyer": 5 if (gm and gm >= 30 and ar and ar > 70 and (cs or 0) >= 1)
                   else (4 if (gm and gm >= 30) else 2),
        "entrant": 5 if (roic and roic - 8 >= 5) else (3 if (roic and roic - 8 >= 0) else 2),
        "substitute": 4 if (inv is not None and inv < 0) else 3,
        "rivalry": 4 if (nm and nm >= 20) else (2 if (sell_er and sell_er > 20) else 3),
    }
    notes = []
    if gm and gm >= 30:
        notes.append(f"毛利率 {gm:.1f}% 且 3 年变动 {gm_tb or 0:+.1f}pp，具备定价权")
    if ap and ap > 70:
        notes.append(f"应付周转天数处于同业 {ap:.0f} 分位，无偿占用上游资金")
    if roic and roic - 8 >= 5:
        notes.append(f"ROIC {roic:.1f}% 高出资本成本 5pp 以上，护城河可量化")
    if sell_er and sell_er > 20:
        notes.append(f"销售费用率 {sell_er:.1f}%，渠道成本高，竞争激烈")
    return f, notes
