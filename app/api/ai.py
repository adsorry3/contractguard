"""无状态 AI 接口：供 Java 侧通过 Feign 调用。

架构边界：数据归 Java 管，能力归 Python 管。本接口只接收条款文本、
返回 fields + risks，不读数据库、不依赖 SQLite，也不写任何表。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.services.ai_review import review_clauses

router = APIRouter(prefix="/api/ai", tags=["AI"])


class ClauseIn(BaseModel):
    """条款入参。"""

    clause_no: str = ""
    title: str = ""
    content: str = ""


class ReviewIn(BaseModel):
    """审查请求体。"""

    clauses: list[ClauseIn] = Field(default_factory=list)


class RiskOut(BaseModel):
    """风险项出参：用 clause_no 关联条款，Java 侧自己映射到 clause_id。"""

    clause_no: str = ""
    risk_type: str = ""
    risk_level: str = ""
    reason: str = ""
    suggestion: str = ""
    confidence: float = 0.0


class ReviewOut(BaseModel):
    """审查响应体。"""

    fields: dict = Field(default_factory=dict)
    risks: list[RiskOut] = Field(default_factory=list)


@router.post("/review", response_model=ReviewOut, summary="无状态 AI 审查")
def ai_review(payload: ReviewIn) -> ReviewOut:
    """接收条款文本，返回字段抽取 + 风险识别结果，不落库。"""
    if not payload.clauses:
        raise HTTPException(status_code=400, detail="clauses 不能为空")

    if not settings.deepseek_api_key:
        raise HTTPException(
            status_code=503,
            detail="LLM 服务未配置：请在项目根目录的 .env 文件里填写 DEEPSEEK_API_KEY 后重启服务",
        )

    clauses = [c.model_dump() for c in payload.clauses]
    result = review_clauses(clauses)
    return ReviewOut(fields=result["fields"], risks=result["risks"])
