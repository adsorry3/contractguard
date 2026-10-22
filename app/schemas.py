"""接口的请求 / 响应模型。"""

from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

T = TypeVar("T")


class ClauseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clause_no: str
    title: str
    content: str
    level: int
    parent_no: str
    page_no: int
    char_start: int
    char_end: int


class ContractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_type: str
    page_count: int
    char_count: int
    status: str
    created_at: datetime


class ContractDetailOut(ContractOut):
    clause_count: int = 0
    clauses: list[ClauseOut] = Field(default_factory=list)


class UploadResponse(BaseModel):
    contract_id: int
    filename: str
    clause_count: int
    page_count: int
    char_count: int


class PageOut(BaseModel, Generic[T]):
    total: int
    page: int = 1
    size: int = 10
    items: list[T]


class RiskItemOut(BaseModel):
    """风险项响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    clause_id: int | None
    risk_type: str
    risk_level: str
    reason: str
    suggestion: str
    confidence: float
    # pending / accepted / rejected：前端用来显示「待处理 / 已采纳 / 已驳回」
    status: str


class FeedbackIn(BaseModel):
    """风险采纳 / 驳回的请求体。"""

    action: Literal["accept", "reject"]
    comment: str = ""


class ChatIn(BaseModel):
    """合同问答请求。"""

    question: str = Field(..., max_length=500)

    @field_validator("question")
    @classmethod
    def _strip_question(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("问题不能为空")
        return v


class AnalyzeResponse(BaseModel):
    """审查结果响应模型。"""

    contract_id: int
    risk_count: int
    fields: dict
    risks: list[RiskItemOut]
    errors: list[str] = []
    elapsed_ms: int
