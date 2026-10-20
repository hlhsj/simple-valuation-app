from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import run

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="A 股企业评价与估值")
    ap.add_argument("codes", nargs="+", help="股票代码，如 600519")
    ap.add_argument("--json", dest="json_dir", default=None,
                    help="结果 JSON 输出目录")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    out_dir = Path(args.json_dir) if args.json_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for c in args.codes:
        print(f"\n===== {c} =====")
        try:
            r = run(c, verbose=args.verbose)
        except Exception as e:
            print(f"  失败：{e}")
            r = {"code": c, "error": str(e)}
        results.append(r)
        if r.get("error"):
            continue
        if r.get("rejected"):
            print(f"  ❌ 淘汰 | {' / '.join(x.split(' ')[0] for x in r['gate']['hard'])}")
        elif r.get("avoid"):
            print("  ⚠ 回避（行业规则）")
        else:
            d, s = r["decision"], r["score"]
            print(f"  {r['profile']['mode']}×{r['profile']['stage']} "
                  f"{s['total']:.1f}{s['grade']} → {d['verdict']}")
        if out_dir:
            (out_dir / f"{c}.json").write_text(
                json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")

    if out_dir:
        (out_dir / "_all.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入 {out_dir}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
