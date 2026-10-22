from __future__ import annotations

import statistics as st
from datetime import date, timedelta
from typing import Any, Sequence

def _series(hist: Sequence[dict[str, Any]], key: str,
            years: float | None = None) -> list[float]:
    cutoff = None
    if years:
        cutoff = (date.today() - timedelta(days=365 * years)).isoformat()
    out: list[float] = []
    for x in hist:
        v = x.get(key)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
            continue
        if cutoff and (str(x.get("TRADE_DATE") or "")[:10] < cutoff):
            continue
        out.append(float(v))
    return sorted(out)

def quantile(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    i = min(int(len(xs) * q), len(xs) - 1)
    return xs[i]

def _band(xs: list[float], cut_top: float | None) -> tuple[list[float], float | None, int]:
    if not cut_top or len(xs) < 10:
        return xs, None, 0
    cut = quantile(xs, cut_top)
    if cut is None:
        return xs, None, 0
    kept = [x for x in xs if x <= cut]
    return kept, cut, len(xs) - len(kept)

def pe_channel(hist: Sequence[dict[str, Any]], *,
               years: float | None = None,
               cut_top: float | None = None) -> dict[str, Any]:
    xs = _series(hist, "PE_TTM", years)
    n_raw = len(xs)
    xs, cut, removed = _band(xs, cut_top)
    return {"p20": quantile(xs, 0.2),
            "p50": st.median(xs) if xs else None,
            "p80": quantile(xs, 0.8),
            "n": len(xs), "n_raw": n_raw, "removed": removed, "cut": cut}

def pb_channel(hist: Sequence[dict[str, Any]], *,
               years: float | None = None,
               cut_top: float | None = None) -> dict[str, Any]:
    xs = _series(hist, "PB_MRQ", years)
    n_raw = len(xs)
    xs, cut, removed = _band(xs, cut_top)
    return {"b20": quantile(xs, 0.2),
            "b50": st.median(xs) if xs else None,
            "b80": quantile(xs, 0.8),
            "n": len(xs), "n_raw": n_raw, "removed": removed, "cut": cut}

def current_percentile(hist: Sequence[dict[str, Any]], key: str,
                       now: float | None) -> float | None:
    xs = _series(hist, key)
    if not xs or not now or now <= 0:
        return None
    return sum(1 for x in xs if x < now) / len(xs)

def series(hist: Sequence[dict[str, Any]], key: str) -> dict[str, Any]:
    rows: list[tuple[str, float]] = []
    for x in hist:
        v = x.get(key)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
            continue
        d = str(x.get("TRADE_DATE") or "")[:10]
        if d:
            rows.append((d, float(v)))
    rows.sort(key=lambda r: r[0])
    if not rows:
        return {"points": [], "n": 0, "start": None, "end": None, "low": None}

    low = min(rows, key=lambda r: r[1])
    return {
        "points": [{"d": d, "v": round(v, 2)} for d, v in rows],
        "n": len(rows),
        "start": rows[0][0],
        "end": rows[-1][0],
        "low": {"d": low[0], "v": round(low[1], 2)},
    }

__all__ = ["pe_channel", "pb_channel", "current_percentile", "quantile", "series"]
