from __future__ import annotations

import statistics as st
from typing import Any, Sequence

def cross_cycle_roe(annuals: Sequence[dict[str, Any]], window: int = 5) -> float | None:
    xs = [p.get("ROEJQ") for p in annuals[:window]
          if isinstance(p.get("ROEJQ"), (int, float))]
    return (st.median(xs) / 100) if xs else None

def normalized_eps(roe: float, bps: float | None) -> float | None:
    return roe * bps if bps else None

def normalized_pe(norm_eps: float | None, price: float | None) -> float | None:
    return (price / norm_eps) if (norm_eps and norm_eps > 0 and price) else None
