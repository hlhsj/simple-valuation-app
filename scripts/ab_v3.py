# -*- coding: utf-8 -*-
"""v3.0 低分红修正的同源 A/B：同一时刻、同一份数据，只切 `pe_low_b` 开/关。

目的
    证明修正只作用于「低分红 + ROE 高于要求回报」的公司，
    分红正常的企业（茅台 b=0.62、海天 0.69、神华 0.81…）结果必须逐位不变。

用法：python scripts/ab_v3.py [--only 600519]
输出：scripts/output/ab_v3.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "src"))

from stock_value_estimator.config import params  # noqa: E402
from stock_value_estimator.pipeline import run  # noqa: E402

SAMPLES = [
    ("600519", "贵州茅台"), ("000858", "五粮液"), ("600809", "山西汾酒"),
    ("603288", "海天味业"), ("600887", "伊利股份"), ("600276", "恒瑞医药"),
    ("300760", "迈瑞医疗"), ("600036", "招商银行"), ("600919", "江苏银行"),
    ("601398", "工商银行"), ("601318", "中国平安"), ("600030", "中信证券"),
    ("601668", "中国建筑"), ("000333", "美的集团"), ("000651", "格力电器"),
    ("300750", "宁德时代"), ("002594", "比亚迪"), ("601012", "隆基绿能"),
    ("688981", "中芯国际"), ("688041", "海光信息"), ("002475", "立讯精密"),
    ("002460", "赣锋锂业"), ("600019", "宝钢股份"), ("601857", "中国石油"),
    ("600900", "长江电力"), ("601088", "中国神华"), ("600585", "海螺水泥"),
    ("002027", "分众传媒"), ("600398", "海澜之家"), ("605499", "东鹏饮料"),
    ("600415", "小商品城"), ("603019", "中科曙光"), ("000977", "浪潮信息"),
    ("300274", "阳光电源"), ("300059", "东方财富"),
]

KEYS = ("target", "fair_low", "fair_high", "buy", "fair_pe", "verdict", "b", "b_used")


def snap(code: str) -> dict:
    d = run(code)
    v, dec, sc = d.get("valuation") or {}, d.get("decision") or {}, d.get("score") or {}
    pick = lambda x: round(x, 2) if isinstance(x, (int, float)) else x
    return {
        "total": round(sc["total"], 1) if sc.get("total") is not None else None,
        "grade": sc.get("grade"),
        "target": pick(v.get("target")),
        "fair_low": pick(v.get("fair_low")),
        "fair_high": pick(v.get("fair_high")),
        "buy": pick(dec.get("buy")),
        "fair_pe": pick(v.get("fair_pe")),
        "verdict": dec.get("verdict"),
        "b": pick(v.get("b")),
        "b_used": pick(v.get("b_used")),
        "rejected": bool(d.get("rejected")),
        "avoid": bool(d.get("avoid")),
    }


def main() -> None:
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    cfg = params()["pe_low_b"]
    orig = dict(cfg)
    rows = []

    for code, nm in SAMPLES:
        if only and code != only:
            continue
        try:
            cfg.update(orig)                       # 开启
            on = snap(code)
            # 关闭：阈值置 0 → 任何 b ≥ 0 都不满足「b < 阈值」，等于全禁
            # （曾误写成 9.99，反而让所有股票都进修正区，A/B 结果全废）
            cfg["b_threshold"] = 0.0
            off = snap(code)
            cfg.update(orig)
        except Exception as e:                     # noqa: BLE001
            print(f"{nm} {code}  ERR {type(e).__name__}: {e}", flush=True)
            continue

        diffs = [k for k in KEYS if on[k] != off[k]]
        rows.append({"code": code, "name": nm, "on": on, "off": off, "diff": diffs})
        if diffs:
            changed = [k for k in diffs if k not in ("b_used",)]
            tag = "  ← 估值变化" if changed else ""
            print(f"{nm:<6}{code}  b={on['b']}→{on['b_used']}  "
                  f"公平价 {off['target']}→{on['target']}  "
                  f"{(off['verdict'] or '')[:10]} → {(on['verdict'] or '')[:10]}{tag}", flush=True)
        else:
            print(f"{nm:<6}{code}  b={on['b']}  无变化", flush=True)

    out = BASE / "scripts" / "output" / "ab_v3.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    moved = [r for r in rows if [k for k in r["diff"] if k != "b_used"]]
    print(f"\n{'='*70}")
    print(f"样本 {len(rows)} 只；估值受影响 {len(moved)} 只")
    for r in moved:
        print(f"  {r['name']}: b {r['off']['b']}→{r['on']['b_used']}  "
              f"公平价 {r['off']['target']}→{r['on']['target']}  "
              f"判定 {r['off']['verdict']} → {r['on']['verdict']}")


if __name__ == "__main__":
    main()
