"""LangGraph 状态定义 + 内部 Pydantic 校验模型。

重要约束：State 里只放可序列化的 dict，绝不放 SQLAlchemy ORM 对象。
理由：LangGraph 的 checkpointer 会对 State 序列化，ORM 实例不可序列化，
在 InMemorySaver 下会报错或静默丢数据；阶段 3 换成持久化 checkpointer 时一定失败。
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field


class FieldExtraction(BaseModel):
    """合同关键字段抽取结果（找不到的填 null，不要编造）。"""

    party_a: str | None = None               # 甲方
    party_b: str | None = None               # 乙方
    amount: str | None = None                # 合同金额（带货币单位）
    payment_method: str | None = None        # 付款方式
    payment_term: str | None = None          # 付款账期（带单位）
    penalty_rate: str | None = None          # 违约金比例（带百分号）
    contract_term: str | None = None         # 合同期限
    jurisdiction: str | None = None          # 管辖地
    acceptance_standard: str | None = None   # 验收标准


class RiskJudgement(BaseModel):
    """单条条款的风险判定结果（detect_risk 提示词的输出结构）。"""

    is_risk: bool = False
    risk_type: str = ""                                    # 只能从候选类型中选
    risk_level: Literal["high", "medium", "low"] = "medium"
    reason: str = ""                                       # 必须引用条款原文
    suggestion: str = ""                                   # 可直接替换原文的措辞
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class State(TypedDict):
    """审查流程图的状态。

    - clauses / risks 都用 dict，保证可序列化；
    - errors 用 operator.add 累加，两个节点各自的错误都能保留，不被覆盖。
    """

    contract_id: int
    clauses: list[dict]
    fields: dict
    risks: list[dict]
    errors: Annotated[list[str], operator.add]
