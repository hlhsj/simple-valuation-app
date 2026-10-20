from __future__ import annotations

from typing import Sequence

from ..config import anchors as anchors_cfg

def clip(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))

def score_anchors(v: float | None,
                  points: Sequence[Sequence[float]] | None = None,
                  name: str | None = None) -> float | None:
    if v is None:
        return None
    if points is None:
        if not name:
            raise ValueError("需提供 points 或 name")
        raw = anchors_cfg().get(name)
        if not raw:
            raise KeyError(f"anchors.yaml 中缺少 {name}")
        points = raw
    pts = sorted((float(a), float(b)) for a, b in points)
    if v <= pts[0][0]:
        return clip(pts[0][1])
    if v >= pts[-1][0]:
        return clip(pts[-1][1])
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= v <= x1:
            if x1 == x0:
                return clip(y1)
            return clip(y0 + (y1 - y0) * (v - x0) / (x1 - x0))
    return clip(pts[-1][1])

def pct_rank(v: float | None, arr: Sequence[float | None],
             higher_better: bool = True) -> float | None:
    if v is None:
        return None
    xs = [x for x in arr if x is not None]
    if len(xs) < 3:
        return None
    rank = sum(1 for x in xs if x < v) / len(xs)
    return clip(rank * 100 if higher_better else (1 - rank) * 100)

def cagr(v0: float | None, v1: float | None, years: int) -> float | None:
    if not v0 or not v1 or years <= 0:
        return None
    if v0 <= 0 or v1 <= 0:
        return None
    return (v1 / v0) ** (1 / years) - 1

def weighted(pairs: Sequence[tuple[float | None, float]]) -> float | None:
    num = den = 0.0
    for v, w in pairs:
        if v is None or w is None:
            continue
        num += v * w
        den += w
    return num / den if den else None

def soft_clamp(v: float | None, hi: float | None,
               k: float | None = None) -> float | None:
    if v is None:
        return None
    if k is None:
        from ..config import params
        k = params().get("soft_clamp_k", 0.33)
    if hi is not None and v > hi:
        return hi + (v - hi) * k
    return v

def trend_consistency_score(state: str | None) -> float:
    table = anchors_cfg().get("trend_consistency") or {}
    return float(table.get(state or "unknown", 55))

def cf_stability_score(neg_years: int) -> float:
    table = anchors_cfg().get("cf_neg_years") or {}
    items = sorted((int(k), float(v)) for k, v in table.items())
    if not items:
        return 55.0
    for k, v in items:
        if neg_years <= k:
            return v
    return items[-1][1]
