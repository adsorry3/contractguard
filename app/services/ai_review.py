"""无状态 AI 审查：clauses -> fields + risks（纯函数，不碰数据库）。

复用 graph/nodes 里的字段抽取与风险判定逻辑，但不走 LangGraph 的
checkpointer（无状态接口，不需要会话）。供 /api/ai/review 调用。

关键转换：
    - 入参 clauses 只有 clause_no / title / content，判定逻辑用 clause_id 做去重锚点，
      这里用 clause_no 充当占位 clause_id；
    - 输出 risks 用 clause_no 关联条款，risk_level 统一转大写（与 MySQL/Java 侧一致）。
"""

from __future__ import annotations

import logging

from app.graph.nodes import detect_risks_node, extract_fields_node

logger = logging.getLogger(__name__)


def review_clauses(clauses: list[dict]) -> dict:
    """把条款列表转成 {fields, risks}。

    返回的 risks 每项字段：clause_no / risk_type / risk_level(大写) / reason /
    suggestion / confidence，不携带 clause_id（由 Java 侧自己映射）。
    """
    # 规范化：补占位 clause_id（= clause_no），供 screen_candidates / detect_risks_node 去重
    normalized = []
    for idx, clause in enumerate(clauses):
        clause_no = (clause.get("clause_no") or "").strip() or f"第{idx + 1}条"
        normalized.append(
            {
                "clause_id": clause_no,  # 占位：判定逻辑用它做去重锚点
                "clause_no": clause_no,
                "title": clause.get("title") or "",
                "content": clause.get("content") or "",
            }
        )

    state = {
        "contract_id": 0,
        "clauses": normalized,
        "fields": {},
        "risks": [],
        "errors": [],
    }

    fields_result = extract_fields_node(state)
    risks_result = detect_risks_node(state)

    risks = []
    for item in risks_result.get("risks") or []:
        risks.append(
            {
                # 判定逻辑写入的 clause_id 就是占位的 clause_no，直接作为 clause_no 输出
                "clause_no": item.get("clause_id") or "",
                "risk_type": item.get("risk_type") or "",
                "risk_level": (item.get("risk_level") or "medium").upper(),
                "reason": item.get("reason") or "",
                "suggestion": item.get("suggestion") or "",
                "confidence": float(item.get("confidence") or 0.0),
            }
        )

    return {
        "fields": fields_result.get("fields") or {},
        "risks": risks,
    }
