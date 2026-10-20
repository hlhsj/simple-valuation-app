from __future__ import annotations

from typing import Any

from ..config import params

P = params()

def judge(grade_: str, stage: str, trend_state: str | None,
          risk_level: str, soft_count: int,
          price: float, fair_high: float | None, fair_low: float | None,
          buy: float | None, e: float | None, r: float,
          invalid: str | None = None) -> str:
    if invalid:
        return "无法定价（主模型失效，不出区间与买点）"
    if grade_ == "D":
        return "回避（六维 D 级，质量不达标）"
    if stage == "衰退期":
        return "回避（衰退期，PB 仅用于判断清算价值，不构成买入）"
    if trend_state == "collapse":
        return "回避（由盈转亏，PE/PB 模型同时失效）"
    if risk_level == "高危":
        return f"回避（L1 减分项 {soft_count} 项叠加，高危）"
    if fair_high and price > fair_high:
        return f"不追（高于合理区间上沿 {price/fair_high-1:+.1%}）"
    if e is not None and e < 0:
        return "不出手（期望收益为负）"
    if e is not None and e < r:
        return "不出手（期望收益低于要求回报）"
    if buy and price <= buy:
        if trend_state == "inflection":
            return "观察（趋势拐点，暂缓建仓——先等一期财报确认是否止跌）"
        return "小仓试探（C 级，≤5% 仓位）" if grade_ == "C" else "分批建仓"
    if fair_low and price <= fair_low:
        return "接近买点（已入区间下沿，等待安全边际）"
    return "合理区间内（持有，不新增）"
