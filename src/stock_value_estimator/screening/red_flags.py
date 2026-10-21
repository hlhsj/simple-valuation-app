from __future__ import annotations

import re
import statistics as st
from datetime import date, timedelta
from typing import Any

from ..config import params

P = params()

def profit_crashes(annuals: list[dict[str, Any]]) -> list[tuple[str, float]]:
    cfg = P.get("crash", {})
    lookback, drop = cfg.get("lookback", 8), cfg.get("drop", -0.40)
    hits: list[tuple[str, float]] = []
    for i in range(min(lookback - 1, len(annuals) - 1)):
        cur, prev = annuals[i].get("PARENTNETPROFIT"), annuals[i + 1].get("PARENTNETPROFIT")
        if isinstance(cur, (int, float)) and isinstance(prev, (int, float)) and prev > 0:
            ch = cur / prev - 1
            if ch <= drop:
                hits.append((annuals[i]["REPORT_DATE"][:4], ch))
    return hits

def gross_margin_std(annuals: list[dict[str, Any]], window: int = 6) -> float | None:
    gm = [p.get("XSMLL") for p in annuals[:window]
          if isinstance(p.get("XSMLL"), (int, float))]
    return (st.pstdev(gm) / 100) if len(gm) >= 4 else None

def neg_cf_years(cf_rows: dict[str, list[str]] | None,
                 periods: list[str] | None) -> int:
    if not cf_rows or not periods:
        return 0
    row = None
    for name in ("经营活动产生的现金流量净额", "经营活动产生现金流量净额"):
        if name in cf_rows:
            row = cf_rows[name]
            break
        for k in cf_rows:
            if name in k:
                row = cf_rows[k]
                break
        if row:
            break
    if not row:
        return 0
    vals = []
    for i, p in enumerate(periods):
        if p.endswith("1231") and i < len(row):
            try:
                vals.append(float(row[i].replace(",", "")))
            except ValueError:
                pass
    return sum(1 for v in vals[:5] if v < 0)

def int_debt(bs_rows: dict[str, list[str]] | None) -> float | None:
    if not bs_rows:
        return None
    names = ["短期借款", "一年内到期的非流动负债", "长期借款", "应付债券", "租赁负债"]
    total = 0.0
    found = False
    for n in names:
        row = bs_rows.get(n)
        if not row:
            for k in bs_rows:
                if n in k:
                    row = bs_rows[k]
                    break
        if not row:
            continue
        for v in row:
            try:
                total += float(v.replace(",", ""))
                found = True
                break
            except ValueError:
                continue
    return total if found else None

def first_value(rows: dict[str, list[str]] | None, names: list[str]) -> float | None:
    if not rows:
        return None
    for n in names:
        row = rows.get(n)
        if not row:
            for k in rows:
                if n in k:
                    row = rows[k]
                    break
        if not row:
            continue
        for v in row:
            try:
                return float(v.replace(",", ""))
            except ValueError:
                continue
    return None

def unlock_pressure(rows: list[dict[str, Any]] | None,
                    today: date | None = None) -> dict[str, Any]:
    cfg = P.get("unlock", {})
    future_days = int(cfg.get("future_days", 183))
    recent_days = int(cfg.get("recent_days", 60))
    base = today or date.today()

    merged: dict[date, dict[str, Any]] = {}
    for r in rows or []:
        raw = (r.get("FREE_DATE") or "")[:10]
        if not raw:
            continue
        try:
            d = date.fromisoformat(raw)
        except ValueError:
            continue
        ratio = r.get("TOTALSHARES_RATIO")
        if not isinstance(ratio, (int, float)) or ratio <= 0:
            continue
        slot = merged.setdefault(d, {"ratio": 0.0, "types": [], "shares": 0.0})
        slot["ratio"] += float(ratio)
        t = (r.get("FREE_SHARES_TYPE") or "").strip()
        if t and t not in slot["types"]:
            slot["types"].append(t)
        sh = r.get("CURRENT_FREE_SHARES")
        if isinstance(sh, (int, float)):
            slot["shares"] += float(sh)

    events: list[dict[str, Any]] = []
    for d, v in merged.items():
        delta = (d - base).days
        if -recent_days <= delta <= future_days:
            events.append({
                "date": d.isoformat(),
                "days": delta,
                "ratio": round(v["ratio"], 6),
                "shares": round(v["shares"], 2),
                "types": v["types"],
                "when": "future" if delta >= 0 else "recent",
            })
    events.sort(key=lambda x: x["date"])
    worst = max(events, key=lambda x: x["ratio"]) if events else None
    return {"events": events, "worst": worst,
            "worst_ratio": (worst["ratio"] if worst else 0.0),
            "window": {"future_days": future_days, "recent_days": recent_days}}

def _norm_name(name: str | None) -> str:
    s = re.sub(r"[（）()\s]", "", name or "")
    for suf in ("股份有限公司", "有限责任公司", "有限公司", "集团公司", "集团", "公司"):
        s = s.replace(suf, "")
    return s

def _is_controller(holder: str, controllers: list[str]) -> bool:
    h = _norm_name(holder)
    if not h:
        return False
    for c in controllers or []:
        n = _norm_name(c)
        if not n:
            continue
        if h == n:
            return True
        if len(n) >= 4 and (n in h or h in n):
            return True
    return False

def pledge_pressure(rows: list[dict[str, Any]] | None,
                    overall_ratio_pct: float | None,
                    controllers: list[str] | None = None) -> dict[str, Any]:
    cfg = P.get("pledge", {})
    tol = float(cfg.get("tolerance", 0.5))
    overall = float(overall_ratio_pct or 0.0)

    active = [r for r in (rows or []) if r.get("UNFREEZE_STATE") == "未解押"]
    raw = 0.0
    per: dict[str, dict[str, Any]] = {}
    for r in active:
        v = r.get("PF_TSR")
        if not isinstance(v, (int, float)) or v <= 0:
            continue
        raw += float(v)
        name = (r.get("HOLDER_NAME") or "").strip()
        if name:
            slot = per.setdefault(name, {"ratio": 0.0, "control": False,
                                         "hold_ratio": 0.0, "pledged": 0.0, "hold": None})
            slot["ratio"] += float(v)
            hr = r.get("PF_HOLD_RATIO")
            if isinstance(hr, (int, float)) and hr > 0:
                slot["hold_ratio"] += float(hr)
            pn = r.get("PF_NUM")
            if isinstance(pn, (int, float)) and pn > 0:
                slot["pledged"] += float(pn) / 1e4
            hn = r.get("HOLD_NUM")
            if isinstance(hn, (int, float)) and hn > 0:
                slot["hold"] = float(hn)
            if str(r.get("IS_CONTROL_SHAREHOLDER")) == "1":
                slot["control"] = True

    controller_holder: dict[str, Any] | None = None
    controller_holder_name: str | None = None

    trusted = raw <= overall + tol
    if trusted:
        by_holder = sorted(({"name": k, "ratio": round(v["ratio"], 4),
                             "hold_ratio": round(v["hold_ratio"], 4),
                             "pledged_wan": round(v["pledged"], 2),
                             "hold_wan": v["hold"],
                             "control": v["control"]} for k, v in per.items()),
                           key=lambda x: -x["ratio"])
        ctrl_slots = [v for k, v in per.items()
                      if v["control"] or _is_controller(k, controllers or [])]
        controller_holder = max(ctrl_slots, key=lambda x: x["hold_ratio"], default=None)
        if controller_holder is not None:
            for k, v in per.items():
                if v is controller_holder:
                    controller_holder_name = k
                    break
        controller_ratio = sum(v["ratio"] for k, v in per.items()
                               if v["control"] or _is_controller(k, controllers or []))
        note = "" if raw > 0 else "无未解押记录"
    else:
        by_holder = []
        controller_ratio = None
        note = (f"股东质押明细（{raw:.2f}%）与公司整体（{overall:.2f}%）不符，"
                f"疑有未回写的解押记录，改用整体口径")

    return {
        "trusted": trusted,
        "total": round(raw if trusted else overall, 4),
        "detail_total": round(raw, 4),
        "overall": round(overall, 4),
        "by_holder": by_holder,
        "controller_ratio": (round(controller_ratio, 4)
                             if controller_ratio is not None else None),
        "controller_holder_ratio": (round(controller_holder["hold_ratio"], 4)
                                    if controller_holder is not None else None),
        "controller_holder_name": controller_holder_name,
        "controller_holder_pledged_wan": (round(controller_holder["pledged"], 2)
                                          if controller_holder is not None else None),
        "controller_holder_hold_wan": (controller_holder["hold"]
                                       if controller_holder is not None else None),
        "controller_names": list(controllers or []),
        "note": note,
    }

def _parse_num(s: Any) -> float | None:
    if s is None:
        return None
    t = str(s).replace(",", "").strip()
    if not t or t in {"--", "-", "nan", "None"}:
        return None
    try:
        return float(t)
    except ValueError:
        return None

def _annual_map(rows: dict[str, list[str]] | None,
                periods: list[str] | None,
                name: str) -> dict[str, float]:
    if not rows or not periods:
        return {}
    row = rows.get(name)
    if not row:
        return {}
    out: dict[str, float] = {}
    for i, p in enumerate(periods):
        s = str(p)
        if not s.endswith("1231") or i >= len(row):
            continue
        v = _parse_num(row[i])
        if v is not None:
            out[s[:4]] = v
    return out

def ar_inventory_growth(bs_rows: dict[str, list[str]] | None,
                        bs_periods: list[str] | None,
                        pl_rows: dict[str, list[str]] | None,
                        pl_periods: list[str] | None) -> dict[str, Any]:
    cfg = P.get("receivable_inventory", {})
    min_abs = float(cfg.get("min_abs_yi", 1.0)) * 1e8
    min_ratio = float(cfg.get("min_rev_ratio", 0.05))

    ar = _annual_map(bs_rows, bs_periods, "应收票据及应收账款")
    if not ar:
        a = _annual_map(bs_rows, bs_periods, "应收账款")
        b = _annual_map(bs_rows, bs_periods, "应收票据")
        for y in set(a) | set(b):
            ar[y] = a.get(y, 0.0) + b.get(y, 0.0)
    inv = _annual_map(bs_rows, bs_periods, "存货")
    rev = _annual_map(pl_rows, pl_periods, "营业收入")
    if not rev:
        rev = _annual_map(pl_rows, pl_periods, "一、营业总收入")

    years = sorted(set(ar) & set(inv) & set(rev), reverse=True)[:2]
    if len(years) < 2:
        return {"applicable": False,
                "note": "年报期次不足两期，或三表科目缺失（银行/保险无应收存货）"}

    cur, prev = years[0], years[1]
    if rev[prev] <= 0 or ar[prev] < 0 or inv[prev] < 0:
        return {"applicable": False, "note": f"{prev} 年基数异常，无法计算同比"}

    rev_g = rev[cur] / rev[prev] - 1
    out: dict[str, Any] = {"applicable": True, "year": cur, "prev_year": prev,
                           "rev_growth": round(rev_g, 4),
                           "rev_yi": round(rev[cur] / 1e8, 2)}

    for key, series, label in (("receivable", ar, "应收"),
                               ("inventory", inv, "存货")):
        v0, v1 = series[prev], series[cur]
        if v0 <= 0:
            out[key] = {"usable": False}
            continue
        g = v1 / v0 - 1
        ratio = (v1 / rev[cur]) if rev[cur] > 0 else None
        material = v1 >= min_abs and ratio is not None and ratio >= min_ratio
        out[key] = {
            "usable": bool(material and g > 0),
            "growth": round(g, 4),
            "yi": round(v1 / 1e8, 2),
            "rev_ratio": round(ratio, 4) if ratio is not None else None,
            "material": material,
            "gap": round(g - rev_g, 4),
            "label": label,
        }

    cands = [(k, out[k]) for k in ("receivable", "inventory")
             if out.get(k, {}).get("usable")]
    worst = max(cands, key=lambda x: x[1]["gap"], default=(None, None))
    out["worst"] = worst[0]
    out["gap"] = worst[1]["gap"] if worst[1] else None
    return out

# 累计报告期 → 上一期累计（用于还原单季）；Q1 没有上一期
_QUARTER_PREV = {"0630": "0331", "0930": "0630", "1231": "0930"}
_QUARTER_LABEL = {"0331": "Q1", "0630": "Q2", "0930": "Q3", "1231": "Q4"}

def quarter_yoy(periods: list[dict[str, Any]] | None) -> dict[str, Any]:
    """最近一个**单季度**的营收 / 归母同比，供 S10 用单季口径（2026-10-22 新增）。

    为什么不能复用 `_split_quarters`
        它要求一年四季齐全（Q1/H1/Q3/FY），对**当年**（只有一、中、三季报）整年跳过，
        于是 S10 只能退化为累计口径——而「前三季很好、单季转差」恰恰是市场先反应的情形。
        实测：宁德时代 2026Q3，累计营收 +56.2%/归母 +31.6%（不触发 S10），
        单季营收 +58.6%/归母 +14.5%，差距 44pp；三季报发布当晚到次日，股价 −12%。

    算法（F10 是累计数，必须做差）
        Q1 = 一季报；Q2 = 中报 − 一季报；Q3 = 三季报 − 中报；Q4 = 年报 − 三季报
        同比 = 本期单季 ÷ 上年同一单季 − 1；上年同季 ≤ 0 或缺失 → None
    """
    vals: dict[str, dict[str, Any]] = {}
    for p in periods or []:
        d = (p.get("REPORT_DATE") or "")[:10]
        if len(d) >= 10:
            vals[d[:4] + d[5:7] + d[8:10]] = p

    def _single(year: str, mmdd: str, field: str) -> float | None:
        cur = vals.get(f"{year}{mmdd}")
        if cur is None or not isinstance(cur.get(field), (int, float)):
            return None
        prev = _QUARTER_PREV.get(mmdd)
        if prev is None:                      # Q1 本身就是单季
            return float(cur[field])
        base = vals.get(f"{year}{prev}")
        if base is None or not isinstance(base.get(field), (int, float)):
            return None
        return float(cur[field]) - float(base[field])

    # 年报的 Q4 要等次年才完整，对「最新单季」没有时效价值，故只在非年报里取
    keys = sorted((k for k in vals if not k.endswith("1231")), reverse=True)
    if not keys:
        return {"applicable": False, "period": None, "rev_yoy": None, "np_yoy": None}

    k = keys[0]
    y, mmdd = k[:4], k[4:]
    prev_y = str(int(y) - 1)
    out: dict[str, Any] = {"applicable": True, "period": f"{y}{_QUARTER_LABEL[mmdd]}",
                           "rev_yoy": None, "np_yoy": None}
    for field, key in (("TOTALOPERATEREVE", "rev_yoy"), ("PARENTNETPROFIT", "np_yoy")):
        cur_v, base_v = _single(y, mmdd, field), _single(prev_y, mmdd, field)
        if cur_v is None or base_v is None or base_v <= 0:
            continue
        out[key] = cur_v / base_v - 1
    return out

def _split_quarters(periods: list[dict[str, Any]] | None) -> dict[str, dict[str, float]]:
    vals: dict[str, float] = {}
    for p in periods or []:
        d = (p.get("REPORT_DATE") or "")[:10]
        npf = p.get("PARENTNETPROFIT")
        if len(d) >= 10 and isinstance(npf, (int, float)):
            vals[d[:4] + d[5:7] + d[8:10]] = float(npf)

    out: dict[str, dict[str, float]] = {}
    for y in sorted({k[:4] for k in vals}, reverse=True):
        q1, h1 = vals.get(f"{y}0331"), vals.get(f"{y}0630")
        q3, fy = vals.get(f"{y}0930"), vals.get(f"{y}1231")
        if None in (q1, h1, q3, fy):
            continue
        out[y] = {"Q1": q1, "Q2": h1 - q1, "Q3": q3 - h1, "Q4": fy - q3, "FY": fy}
    return out

def quarterly_profile(periods: list[dict[str, Any]] | None) -> dict[str, Any]:
    cfg = P.get("quarterly", {})
    q1_high = float(cfg.get("q1_share_high", 0.40))
    q4_low = float(cfg.get("q4_share_low", 0.10))
    need_years = int(cfg.get("min_years", 2))

    qs = _split_quarters(periods)
    if not qs:
        return {"applicable": False, "front_loaded": False, "single_loss": False,
                "note": "报告期不足，无法还原单季度"}

    years = list(qs)
    front_years: list[str] = []
    for y in years:
        q, fy = qs[y], qs[y]["FY"]
        if fy <= 0:
            break
        if q["Q1"] / fy >= q1_high and q["Q4"] / fy <= q4_low:
            front_years.append(y)
        else:
            break

    latest = years[0]
    cur = qs[latest]
    losses = [(f"Q{i+1}", cur[f"Q{i+1}"]) for i in range(4) if cur[f"Q{i+1}"] < 0]
    single_loss = bool(losses) and cur["FY"] > 0

    return {
        "applicable": True,
        "year": latest,
        "q1_share": round(cur["Q1"] / cur["FY"], 4) if cur["FY"] > 0 else None,
        "q4_share": round(cur["Q4"] / cur["FY"], 4) if cur["FY"] > 0 else None,
        "front_years": front_years,
        "front_loaded": len(front_years) >= need_years,
        "loss_quarters": [(k, round(v / 1e8, 2)) for k, v in losses],
        "single_loss": single_loss,
        "fy_yi": round(cur["FY"] / 1e8, 2),
    }
