from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[3] / "data" / "stock_industry_map.json"

@lru_cache(maxsize=1)
def _load() -> dict[str, str]:
    if not DATA_PATH.exists():
        return {}
    with DATA_PATH.open(encoding="utf-8") as f:
        return json.load(f)

def industry_of(code: str) -> str | None:
    return _load().get(code)

def peers_of(code: str, limit: int | None = None) -> tuple[list[str], str | None]:
    m = _load()
    ind = m.get(code)
    if not ind:
        return [], None
    peers = sorted(k for k, v in m.items() if v == ind)
    if limit:
        peers = peers[:limit]
    return peers, ind

def peer_sample_size(code: str) -> int:
    peers, _ = peers_of(code)
    return max(0, len(peers) - 1)
