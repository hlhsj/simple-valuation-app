from __future__ import annotations

from typing import Any

from ..config import industry_map as imap

def classify(industry_label: str | None,
             latest: dict[str, Any] | None = None) -> tuple[str, list[int]]:
    lab = industry_label or ""
    cfg = imap()
    for rule in cfg.get("mode_rules", []):
        if any(lab.startswith(p) for p in rule.get("prefixes", [])):
            mode, zero = rule["mode"], list(rule.get("zero_pe", [10, 15]))
            break
    else:
        d = cfg.get("default", {})
        mode, zero = d.get("mode", "运营型"), list(d.get("zero_pe", [10, 15]))

    ov = (cfg.get("overrides") or {}).get("product_to_operation") or {}
    if mode == "产品型" and latest:
        gm = latest.get("XSMLL") or 0
        ser = latest.get("SALE_ER_PK") or 0
        if gm < ov.get("gross_margin_max", 22) and ser > ov.get("sale_expense_ratio_min", 18):
            d = cfg.get("default", {})
            mode, zero = "运营型", list(d.get("zero_pe", [10, 15]))
    return mode, zero
