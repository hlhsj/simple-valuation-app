from __future__ import annotations

import statistics as st
from typing import Any, Sequence

def _series(hist: Sequence[dict[str, Any]], key: str) -> list[float]:
    xs = sorted(x[key] for x in hist
                if isinstance(x.get(key), (int, float)) and x[key] > 0)
    return xs

def quantile(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    i = min(int(len(xs) * q), len(xs) - 1)
    return xs[i]

def pe_channel(hist: Sequence[dict[str, Any]]) -> dict[str, float | None]:
    xs = _series(hist, "PE_TTM")
    return {"p20": quantile(xs, 0.2), "p50": st.median(xs) if xs else None,
            "p80": quantile(xs, 0.8), "n": len(xs)}

def pb_channel(hist: Sequence[dict[str, Any]]) -> dict[str, float | None]:
    xs = _series(hist, "PB_MRQ")
    return {"b20": quantile(xs, 0.2), "b50": st.median(xs) if xs else None,
            "b80": quantile(xs, 0.8), "n": len(xs)}

def current_percentile(hist: Sequence[dict[str, Any]], key: str,
                       now: float | None) -> float | None:
    xs = _series(hist, key)
    if not xs or not now or now <= 0:
        return None
    return sum(1 for x in xs if x < now) / len(xs)
