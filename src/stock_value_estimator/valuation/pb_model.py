from __future__ import annotations

from ..scoring.anchors import soft_clamp
from .channel import pb_channel

def gordon_pb(roe: float, r: float, g: float) -> float | None:
    return (roe - g) / (r - g) if r - g > 0.005 else None

def fair_pb(roe: float, r: float, g: float,
            hist: list[dict] | None = None,
            *, ch: dict | None = None) -> tuple[float | None, float | None, str]:
    raw = gordon_pb(roe, r, g)
    if raw is None:
        return None, None, "r − g ≤ 0.5pp，PB 公式失效"
    ch = ch if ch is not None else pb_channel(hist or [])
    b50, b80, b20 = ch["b50"], ch["b80"], ch["b20"]
    if not b50:
        return raw, raw, "纯 PB 模型（无历史通道，置信度低）"
    val = (raw * b50) ** 0.5
    note = "PB 模型与历史中枢几何平均"
    if b20 is not None and b80 is not None:
        before = val
        val = soft_clamp(val, b80)
        if val != before:
            note += "，并软收缩至历史 P80（越界保留 1/3，只压上限不抬下限）"
    return raw, val, note

def normalized_pe(roe: float, bps: float | None, price: float | None) -> tuple[float | None, float | None]:
    norm_eps = roe * bps if bps else None
    norm_pe = (price / norm_eps) if (norm_eps and norm_eps > 0 and price) else None
    return norm_eps, norm_pe
