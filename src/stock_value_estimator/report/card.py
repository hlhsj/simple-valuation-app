from __future__ import annotations

from typing import Any

DIM_LABELS: list[tuple[str, str]] = [
    ("profit", "盈利"), ("cashflow", "现金流"), ("growth", "成长"),
    ("solvency", "偿债"), ("operation", "营运"), ("asset", "资产"),
]

def _f(x, d: int = 2, suffix: str = "") -> str:
    return f"{x:.{d}f}{suffix}" if isinstance(x, (int, float)) else "—"

def _p(x, d: int = 1) -> str:
    return f"{x * 100:.{d}f}%" if isinstance(x, (int, float)) else "—"

def render(r: dict[str, Any]) -> str:
    lines = [f"# {r.get('name', '')}（{r.get('code', '')}）　{r.get('industry') or '—'}"]
    if r.get("error"):
        lines += ["", f"> 失败：{r['error']}"]
        return "\n".join(lines)

    g = r.get("gate") or {}
    lines += ["", f"**风险等级：{g.get('risk_level', '—')}**"
                  f"（硬否决 {len(g.get('hard', []))} 项 / 减分 {len(g.get('soft', []))} 项）"]
    for x in g.get("hard", []):
        lines.append(f"- ✕ {x}")
    for x in g.get("soft", []):
        lines.append(f"- △ {x}")

    if r.get("rejected"):
        lines += ["", "> 硬否决命中即终止，不进入 L2–L5，不产出任何估值数字。"]
        return "\n".join(lines)
    if r.get("avoid"):
        lines += ["", f"> {r.get('reason', '')}"]
        return "\n".join(lines)

    s, p, v, d = r["score"], r["profile"], r["valuation"], r["decision"]

    dims = s.get("dims") or {}
    lines += ["", "## 六维评价", "",
              "| " + " | ".join(label for _, label in DIM_LABELS) + " |",
              "|" + "---|" * len(DIM_LABELS),
              "| " + " | ".join(_f(dims.get(k), 1) for k, _ in DIM_LABELS) + " |",
              "",
              f"**总分 {_f(s['total'], 1)} → {s['grade']} 级**", "",
              f"经营模式 {p['mode']}｜生命周期 {p['stage']}"
              + (f"（{p['substage']}）" if p.get("substage") else "")]

    b_txt = _f(v.get("b"), 3)
    b_used = v.get("b_used")
    if isinstance(b_used, (int, float)) and isinstance(v.get("b"), (int, float)) \
            and abs(b_used - v["b"]) > 0.001:
        b_txt += f"（低分红口径按 {b_used:.3f} 计）"
    lines += ["", "## 估值", "",
              f"主模型 {v['primary']}｜r {_p(v['r'], 2)}｜g {_p(v['g'], 2)}｜b {b_txt}"]

    if v.get("invalid"):
        lines += ["", f"> ✕ {v['invalid']}"]
    else:
        lines += ["", f"合理区间 **{_f(v.get('fair_low'))} – {_f(v.get('fair_high'))}**"
                      f"｜安全边际价位 {_f(d.get('buy'))}｜现价 {_f(r['price'])}"]

    rim = v.get("rim") or {}
    if rim.get("applicable") and v.get("primary") == "PE":
        lines += ["", f"RIM 对照：隐含 PE {_f(rim.get('pe_implied'))}×"
                      f"（戈登 {_f(v.get('fair_pe_gordon'))}×，不参与定价）"]

    lines += ["", "## 决策", "", f"**{d['verdict']}**"]
    if d.get("E") is not None:
        lines += ["", f"E(R) {_p(d['E'])}｜要求回报 {_p(v['r'], 2)}"
                      f"｜行情 {d.get('market_state', '—')}"]
    if v.get("caveat"):
        lines += ["", f"> ⚠ {v['caveat']}"]
    return "\n".join(lines)
