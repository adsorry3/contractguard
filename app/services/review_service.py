"""职责：审查流程的可复用逻辑（同步 analyze 与异步 review 共用）。"""

from __future__ import annotations

import logging

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Contract, RiskItem
from app.services import redis_client

logger = logging.getLogger(__name__)


def build_state(contract_id: int, clauses) -> dict:
    """ORM 条款列表 → 固定键 dict + 初始 state。"""
    clause_dicts = [
        {
            "clause_id": c.id,
            "clause_no": c.clause_no,
            "title": c.title,
            "content": c.content,
            "char_start": c.char_start,
            "char_end": c.char_end,
        }
        for c in clauses
    ]
    return {
        "contract_id": contract_id,
        "clauses": clause_dicts,
        "fields": {},
        "risks": [],
        "errors": [],
    }


def persist_result(db: Session, contract_id: int, result: dict) -> int:
    """批量删旧 risk_item、写新、更新合同状态，返回风险条数。"""
    risk_dicts = result.get("risks") or []

    # 幂等：批量删除旧风险项
    db.execute(delete(RiskItem).where(RiskItem.contract_id == contract_id))

    for item in risk_dicts:
        db.add(
            RiskItem(
                contract_id=contract_id,
                clause_id=item.get("clause_id"),
                risk_type=item.get("risk_type", ""),
                risk_level=item.get("risk_level", "medium"),
                reason=item.get("reason", ""),
                suggestion=item.get("suggestion", ""),
                law_ref="",
                confidence=float(item.get("confidence", 0.0) or 0.0),
            )
        )

    contract = db.get(Contract, contract_id)
    if contract is not None:
        contract.status = "analyzed"
    db.commit()

    # 清报告缓存（Redis 挂了只 warning，不影响写库）
    _delete_report_cache(contract_id)

    return len(risk_dicts)


def _delete_report_cache(contract_id: int) -> None:
    """删除该合同的报告缓存；Redis 挂了只 warning，不影响写库。"""
    try:
        redis_client.get_redis().delete(redis_client.key("report", contract_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("删除报告缓存失败：%s", exc)
