"""职责：10 类风险的关键词粗筛规则 + screen_candidates。

「规则粗筛 + LLM 精判」两段式：关键词零成本筛出候选条款，LLM 只精判候选。
liability_cap_missing 是「缺失类风险」，单条条款关键词命中不了，用全文负向判断。
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskRule:
    """一条风险粗筛规则：risk_type + 中文名 + 正则列表（任一命中即候选）。"""

    risk_type: str
    name_cn: str
    patterns: tuple[str, ...]


# 9 类「存在型」风险：条款里出现这些表述就进入候选。
# 正则宽松命中即可，精确判断交给 LLM。
EXISTENCE_RULES: tuple[RiskRule, ...] = (
    RiskRule(
        "penalty_too_high",
        "违约金比例过高",
        (
            r"违约金.{0,50}?(?:百分之[三四五六七八九十]|\d{2,}\s*%)",
            r"(?:百分之[三四五六七八九十]|\d{2,}\s*%).{0,50}?违约金",
        ),
    ),
    RiskRule(
        "payment_term_too_long",
        "付款账期过长",
        (
            r"\d{2,}\s*日.{0,20}?(?:支付|付款|账期)",
            r"(?:支付|付款|账期).{0,20}?\d{2,}\s*日",
        ),
    ),
    RiskRule(
        "unilateral_termination",
        "单方解除权不对等",
        (
            r"(?:单方|单方面|随时).{0,8}(?:解除|终止|取消)",
            r"(?:解除|终止).{0,20}?无需.{0,12}(?:承担|违约责任)",
        ),
    ),
    RiskRule(
        "jurisdiction_unfair",
        "管辖约定不利",
        (
            r"(?:乙方|被告|对方|卖方|供应商).{0,8}所在地.{0,10}(?:人民法院|法院|仲裁)",
        ),
    ),
    RiskRule(
        "confidentiality_vague",
        "保密条款模糊",
        (
            r"保密.{0,30}?(?:合理期限|另行|视情况|适当|酌情)",
        ),
    ),
    RiskRule(
        "ip_ownership_unclear",
        "知识产权归属不明",
        (
            r"(?:知识产权|著作权|专利|商标|软件).{0,30}?(?:另行|协商|待定|后续.{0,8}确定|归.{0,6}方)",
        ),
    ),
    RiskRule(
        "acceptance_vague",
        "验收标准模糊",
        (
            r"验收.{0,30}?(?:另行|协商|确认|约定|待定|另议|为准)",
        ),
    ),
    RiskRule(
        "auto_renewal",
        "自动续约无通知期",
        (
            r"自动续约|自动续期|自动顺延|期满.{0,6}自动",
        ),
    ),
    RiskRule(
        "force_majeure_broad",
        "不可抗力范围过宽",
        (
            r"不可抗力.{0,40}?(?:包括但不限于|包含|包括).{0,20}(?:政策|市场|经济|价格|行情)",
            r"(?:政策调整|市场变化|经济形势|价格波动).{0,10}(?:纳入|属于|构成).{0,10}不可抗力",
        ),
    ),
)

# 缺失类风险：缺少赔偿上限。
# 全文若都没有这些词，才判定「缺上限」，并挂到违约责任相关条款上。
LIABILITY_CAP_MISSING_FORBIDDEN: tuple[str, ...] = (
    "赔偿上限",
    "责任上限",
    "最高赔偿",
    "赔偿限额",
    "赔偿责任限额",
    "赔偿总额",
    "责任限额",
    "累计赔偿",
)
# 缺失类风险挂靠到哪类条款：按顺序优先找含这些关键词的条款
LIABILITY_CAP_MISSING_ANCHOR: tuple[str, ...] = (
    "违约责任",
    "违约金",
    "合同解除",
    "赔偿",
    "责任",
)


def screen_candidates(clauses: list[dict]) -> list[tuple[dict, list[str]]]:
    """粗筛：返回 (条款 dict, 命中的候选风险类型列表)。

    - 对每条条款，用存在型规则的正则匹配 content，命中则记录对应 risk_type；
    - 单独处理 liability_cap_missing：全文负向判断 + 挂靠最相关条款。
    """
    # 预编译存在型规则的正则
    compiled: list[tuple[str, tuple[re.Pattern[str], ...]]] = [
        (rule.risk_type, tuple(re.compile(p) for p in rule.patterns))
        for rule in EXISTENCE_RULES
    ]

    candidates: list[tuple[dict, list[str]]] = []
    for clause in clauses:
        content = clause.get("content") or ""
        hit_types: list[str] = []
        for risk_type, patterns in compiled:
            if any(pattern.search(content) for pattern in patterns):
                hit_types.append(risk_type)
        if hit_types:
            candidates.append((clause, hit_types))

    # 缺失类：全文负向判断
    full_text = "\n".join(clause.get("content") or "" for clause in clauses)
    has_cap = any(word in full_text for word in LIABILITY_CAP_MISSING_FORBIDDEN)
    if not has_cap:
        anchor = _find_anchor_clause(clauses)
        if anchor is not None:
            _append_candidate(candidates, anchor, "liability_cap_missing")

    return candidates


def _find_anchor_clause(clauses: list[dict]) -> dict | None:
    """找到缺失类风险要挂靠的条款：优先违约责任 / 解除相关，其次第一条。"""
    for keyword in LIABILITY_CAP_MISSING_ANCHOR:
        for clause in clauses:
            if keyword in (clause.get("content") or ""):
                return clause
    return clauses[0] if clauses else None


def _append_candidate(
    candidates: list[tuple[dict, list[str]]], clause: dict, risk_type: str
) -> None:
    """把 risk_type 追加到 clause 对应的候选里；若 clause 还没候选则新建一项。"""
    clause_id = clause.get("clause_id")
    for existing_clause, types in candidates:
        if existing_clause.get("clause_id") == clause_id:
            types.append(risk_type)
            return
    candidates.append((clause, [risk_type]))
