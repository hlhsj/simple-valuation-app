from __future__ import annotations

AVOID_INDUSTRIES = ("J68",)

PB_MODES = ("项目型", "资本型")

def route(mode: str, stage: str, industry_label: str | None = None
          ) -> tuple[str, list[str], str]:
    lab = industry_label or ""
    if any(lab.startswith(p) for p in AVOID_INDUSTRIES):
        return "NONE", [], "寿险/健康险为主：PE 与 PB 均受精算假设扭曲，按教程建议新手回避"

    if mode in PB_MODES:
        aux = ["DIVIDEND_YIELD"]
        if mode == "资本型":
            aux += ["NPL", "PROVISION"]
            reason = "资本型：净资产是主要价值来源，PB 为主；股息率与资产质量校验"
        else:
            aux += ["NORMALIZED_PE", "PB_CHANNEL"]
            reason = "项目型/周期：利润随周期剧烈波动，PE 口径失效，改用 PB + 正常化 PE"
        if stage == "衰退期":
            reason += "（衰退期：PB 仅用于判断清算价值，不构成买入）"
        return "PB", aux, reason

    aux = ["DIVIDEND_YIELD", "PE_CHANNEL"]
    if stage == "成长期":
        aux.append("PEG")
        reason = "成长期：PE 为主，PEG 校验增速是否支撑估值"
    else:
        reason = "产品型/运营型：盈利可预测，PE 为主；股息率与历史通道校验"
    return "PE", aux, reason
