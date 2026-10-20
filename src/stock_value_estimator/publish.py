from __future__ import annotations

import math
import re
from datetime import datetime, timezone, timedelta

def _num(v) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return f if math.isfinite(f) else None
    return None

def _json(v):
    if v is None:
        return None
    if isinstance(v, dict):
        return {k: _json(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_json(x) for x in v]
    return _num(v) if isinstance(v, float) else v

def convert(d: dict) -> dict:
    profile = d.get("profile") or {}
    val = d.get("valuation") or {}
    dec = d.get("decision") or {}
    score = d.get("score") or {}
    gate = d.get("gate") or {}
    trend = d.get("trend") or {}

    raw_name = d.get("name") or ""
    row = {
        "code": d.get("code"),
        "name": re.sub(r"\s+", "", raw_name),
        "price": _num(d.get("price")),
        "pe": _num(d.get("pe")),
        "pb": _num(d.get("pb")),
        "industry": d.get("industry"),
        "mode": profile.get("mode"),
        "stage": profile.get("stage"),
        "substage": profile.get("substage"),
        "score_total": _num(score.get("total")),
        "grade": score.get("grade"),
        "dims": _json(score.get("dims")),
        "gate": _json(gate) if gate else None,
        "primary_model": val.get("primary"),
        "r": _num(val.get("r")),
        "g": _num(val.get("g")),
        "b": _num(val.get("b")),
        "target": _num(val.get("target")),
        "fair_low": _num(val.get("fair_low")),
        "fair_high": _num(val.get("fair_high")),
        "buy": _num(dec.get("buy")),
        "e_return": _num(dec.get("E")),
        "market_state": dec.get("market_state"),
        "verdict": dec.get("verdict"),
        "trend": _json(trend) if trend else None,
        "rim": _json(val.get("rim")),
        "ev_ebitda": _json(val.get("ev_ebitda")),
        "caveat": val.get("caveat"),
        "invalid": val.get("invalid"),
        "rejected": bool(d.get("rejected")),
        "avoid": bool(d.get("avoid")),
        "avoid_reason": d.get("reason"),
        "updated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
    }
    if row["rejected"]:
        row["primary_model"] = row["primary_model"] or None
        row["verdict"] = row["verdict"] or "淘汰"
    elif row["avoid"]:
        row["verdict"] = row["verdict"] or "回避"
    return row

__all__ = ["convert"]
