"""ORM 模型：合同审查系统的 7 张核心表。

阶段 0 先在 SQLite 上跑通；以后迁移到 PostgreSQL / MySQL 时，
只要改 .env 里的 DATABASE_URL，这张表结构不用动。
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now() -> datetime:
    return datetime.now()


class Contract(Base):
    """合同主表。"""

    __tablename__ = "contract"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), default="")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    # uploaded / parsing / analyzing / done / failed
    status: Mapped[str] = mapped_column(String(32), default="uploaded", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    clauses: Mapped[list["Clause"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )
    risks: Mapped[list["RiskItem"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )


class Clause(Base):
    """合同条款：切分后的最小检索单元。"""

    __tablename__ = "clause"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contract.id", ondelete="CASCADE"), index=True
    )
    clause_no: Mapped[str] = mapped_column(String(32), default="")
    title: Mapped[str] = mapped_column(String(255), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    level: Mapped[int] = mapped_column(Integer, default=1)
    parent_no: Mapped[str] = mapped_column(String(32), default="")
    page_no: Mapped[int] = mapped_column(Integer, default=0)
    char_start: Mapped[int] = mapped_column(Integer, default=0)
    char_end: Mapped[int] = mapped_column(Integer, default=0)
    # 先存 JSON 字符串（阶段 5 用 numpy 暴力余弦）；
    # 迁到 PostgreSQL 时可换成 pgvector 的 Vector(1024)
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    contract: Mapped["Contract"] = relationship(back_populates="clauses")

    __table_args__ = (Index("ix_clause_contract_no", "contract_id", "clause_no"),)


class RiskItem(Base):
    """识别出的风险项。"""

    __tablename__ = "risk_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contract.id", ondelete="CASCADE"), index=True
    )
    clause_id: Mapped[int | None] = mapped_column(
        ForeignKey("clause.id", ondelete="SET NULL"), nullable=True
    )
    # 10 类风险，取值见项目文档
    risk_type: Mapped[str] = mapped_column(String(64), index=True)
    # high / medium / low
    risk_level: Mapped[str] = mapped_column(String(16), default="medium")
    reason: Mapped[str] = mapped_column(Text, default="")
    suggestion: Mapped[str] = mapped_column(Text, default="")
    law_ref: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # pending / accepted / rejected
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    contract: Mapped["Contract"] = relationship(back_populates="risks")


class ReviewTask(Base):
    """审查任务：异步执行的进度与状态。"""

    __tablename__ = "review_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contract.id", ondelete="CASCADE"), index=True
    )
    # pending / running / waiting_review / done / failed
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(64), default="")
    error_text: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Feedback(Base):
    """人工复核记录：采纳 / 驳回。"""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    risk_item_id: Mapped[int] = mapped_column(
        ForeignKey("risk_item.id", ondelete="CASCADE"), index=True
    )
    # accept / reject
    action: Mapped[str] = mapped_column(String(16))
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class LawDoc(Base):
    """法规库：给风险判定提供依据。"""

    __tablename__ = "law_doc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    article_no: Mapped[str] = mapped_column(String(64), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class EvalResult(Base):
    """评测结果：每次跑评测落一条。"""

    __tablename__ = "eval_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_recall: Mapped[float] = mapped_column(Float, default=0.0)
    false_positive_rate: Mapped[float] = mapped_column(Float, default=0.0)
    field_accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ContractProfile(Base):
    """合同字段抽取结果（fields）的 JSON 存储。

    阶段 2 抽取的字段（甲方/乙方/金额/账期等）单独落这张表，
    避免给 contract 表加列（create_all 不会给已有表加列）。
    """

    __tablename__ = "contract_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("contract.id", ondelete="CASCADE"), unique=True, index=True
    )
    payload: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
