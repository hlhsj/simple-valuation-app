from __future__ import annotations

from ..scoring.anchors import soft_clamp
from .channel import pe_channel

def gordon_pe(b: float, r: float, g: float) -> float | None:
    return b / (r - g) if r - g > 0.005 else None

def fair_pe(b: float, r: float, g: float,
            hist: list[dict] | None = None,
            *, ch: dict | None = None) -> tuple[float | None, float | None, str]:
    raw = gordon_pe(b, r, g)
    if raw is None:
        return None, None, "r − g ≤ 0.5pp，戈登公式失效"
    ch = ch if ch is not None else pe_channel(hist or [])
    p50, p80, p20 = ch["p50"], ch["p80"], ch["p20"]
    if not p50:
        return raw, raw, "纯戈登（无历史通道，置信度低）"
    val = (raw * p50) ** 0.5
    note = "戈登与历史中枢几何平均"
    if p20 is not None and p80 is not None:
        before = val
        val = soft_clamp(val, p80)
        if val != before:
            note += "，并软收缩至历史 P80（越界保留 1/3，只压上限不抬下限）"
    return raw, val, note
