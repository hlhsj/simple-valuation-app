from __future__ import annotations

from typing import Any

from ..config import params

P = params()

PROB = {"牛市": (0.45, 0.40, 0.15),
        "平市": (0.10, 0.80, 0.10),
        "熊市": (0.15, 0.40, 0.45)}

def market_state(idx_pct: float) -> str:
    return "牛市" if idx_pct < 0.30 else ("熊市" if idx_pct > 0.70 else "平市")

def expected_return(price: float, res: dict[str, Any], dy: float | None,
                    state: str) -> tuple[float | None, tuple, tuple]:
    prob = PROB.get(state, PROB["平市"])
    target = res.get("target")
    primary = res.get("primary")
    is_pb = primary == "PB"
    is_ev = primary == "EV/EBITDA"
    if is_pb:
        unit = res.get("bps")
        fair_mult = res.get("fair_pb")
        p20, p80 = res.get("b20"), res.get("b80")
    elif is_ev:
        ev = res.get("ev_ebitda") or {}
        unit = (ev.get("ebitda") / ev.get("shares")) if ev.get("shares") else None
        fair_mult = ev.get("mult")
        p20 = p80 = None
    else:
        unit = res.get("eps_ttm")
        fair_mult = res.get("fair_pe")
        p20, p80 = res.get("p20"), res.get("p80")

    bull_v = bear_v = None
    span = P.get("scenario", {}).get("span", 0.30)
    if fair_mult and unit and fair_mult > 0:
        m_bull = fair_mult * (1 + span)
        m_bear = fair_mult * (1 - span)
        if p80:
            m_bull = min(m_bull, p80)
        if p20:
            m_bear = max(m_bear, p20)
        bull_v, bear_v = m_bull * unit, m_bear * unit

    r_flat = (target / price - 1 + (dy or 0)) if target else None
    r_bull = (bull_v / price - 1 + (dy or 0)) if bull_v else None
    r_bear = (bear_v / price - 1 + (dy or 0)) if bear_v else None
    if None in (r_bull, r_flat, r_bear):
        return None, prob, (r_bull, r_flat, r_bear)
    e = prob[0] * r_bull + prob[1] * r_flat + prob[2] * r_bear
    return e, prob, (r_bull, r_flat, r_bear)
