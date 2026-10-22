"""合同接口：上传、列表、详情、条款列表。

上传流程：校验 → 落盘 → 解析 → 切分 → 入库 → 返回摘要。
本阶段不涉及 LLM，纯文档处理，所以可以同步完成。
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.graph.build import get_graph
from app.models import Clause, Contract, ReviewTask, RiskItem
from app.schemas import (
    AnalyzeResponse,
    ClauseOut,
    ContractDetailOut,
    ContractOut,
    PageOut,
    RiskItemOut,
    UploadResponse,
)
from app.services import redis_client, review_service
from app.services.parser import SUPPORTED_EXTENSIONS, parse_document
from app.services.splitter import split_clauses
from app.services.task_runner import run_review

logger = logging.getLogger(__name__)

# 审查分布式锁 TTL（秒）：要大于大合同的最长审查时长，避免锁提前过期导致重复审查
_REVIEW_LOCK_TTL = 300

router = APIRouter(prefix="/api/contracts", tags=["合同"])


@router.post("", response_model=UploadResponse, summary="上传合同并完成解析、切分")
def upload_contract(
    file: UploadFile = File(..., description="PDF 或 DOCX 格式的合同文件"),
    db: Session = Depends(get_db),
) -> UploadResponse:
    """上传 → 落盘 → 解析 → 切分 → 入库，同步返回处理结果。

    这里用同步 def 而不是 async def：解析和数据库操作都是阻塞 IO，
    FastAPI 会把同步端点丢进线程池，不会卡住事件循环。
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"只支持 {'、'.join(sorted(SUPPORTED_EXTENSIONS))} 格式，收到的是 {suffix or '未知'}",
        )

    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413, detail=f"文件超过 {settings.max_upload_mb}MB 限制"
        )

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = upload_dir / f"{uuid.uuid4().hex}{suffix}"
    stored_path.write_bytes(content)

    try:
        doc = parse_document(stored_path)
    except Exception as exc:  # noqa: BLE001  解析库抛的异常类型不统一，统一转 422
        raise HTTPException(status_code=422, detail=f"解析失败：{exc}") from exc

    if not doc.text.strip():
        raise HTTPException(
            status_code=422, detail="没有抽取到任何文本，可能是扫描件（需要 OCR）"
        )

    spans = split_clauses(doc)

    contract = Contract(
        filename=file.filename or stored_path.name,
        file_path=str(stored_path),
        file_type=suffix.lstrip("."),
        page_count=doc.page_count,
        char_count=len(doc.text),
        status="parsed",
    )
    db.add(contract)
    db.flush()  # 拿到自增 id，供下面写 clause 用

    db.add_all(
        [
            Clause(
                contract_id=contract.id,
                clause_no=span.clause_no,
                title=span.title,
                content=span.content,
                level=span.level,
                parent_no=span.parent_no,
                page_no=span.page_no,
                char_start=span.char_start,
                char_end=span.char_end,
            )
            for span in spans
        ]
    )
    db.commit()
    db.refresh(contract)

    return UploadResponse(
        contract_id=contract.id,
        filename=contract.filename,
        clause_count=len(spans),
        page_count=contract.page_count,
        char_count=contract.char_count,
    )


@router.get("", response_model=PageOut[ContractOut], summary="合同列表（分页）")
def list_contracts(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    size: int = Query(10, ge=1, le=100, description="每页条数"),
    status: str | None = Query(None, description="按状态过滤"),
    db: Session = Depends(get_db),
) -> PageOut[ContractOut]:
    stmt = select(Contract)
    count_stmt = select(func.count()).select_from(Contract)

    if status:
        stmt = stmt.where(Contract.status == status)
        count_stmt = count_stmt.where(Contract.status == status)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Contract.id.desc()).offset((page - 1) * size).limit(size)
    ).all()

    return PageOut[ContractOut](
        total=total,
        page=page,
        size=size,
        items=[ContractOut.model_validate(row) for row in rows],
    )


@router.get(
    "/{contract_id}", response_model=ContractDetailOut, summary="合同详情（含条款）"
)
def get_contract(contract_id: int, db: Session = Depends(get_db)) -> ContractDetailOut:
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="合同不存在")

    clauses = db.scalars(
        select(Clause).where(Clause.contract_id == contract_id).order_by(Clause.id)
    ).all()

    detail = ContractDetailOut.model_validate(contract)
    detail.clause_count = len(clauses)
    detail.clauses = [ClauseOut.model_validate(c) for c in clauses]
    return detail


@router.get(
    "/{contract_id}/clauses", response_model=list[ClauseOut], summary="合同条款列表"
)
def list_clauses(contract_id: int, db: Session = Depends(get_db)) -> list[ClauseOut]:
    if db.get(Contract, contract_id) is None:
        raise HTTPException(status_code=404, detail="合同不存在")

    clauses = db.scalars(
        select(Clause).where(Clause.contract_id == contract_id).order_by(Clause.id)
    ).all()
    return [ClauseOut.model_validate(c) for c in clauses]


@router.post(
    "/{contract_id}/analyze",
    response_model=AnalyzeResponse,
    summary="审查合同（同步）",
)
def analyze_contract(contract_id: int, db: Session = Depends(get_db)) -> AnalyzeResponse:
    """同步审查：调用图 + 落库，核心逻辑复用 review_service。"""
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="合同不存在")

    clauses = db.scalars(
        select(Clause).where(Clause.contract_id == contract_id).order_by(Clause.id)
    ).all()
    if not clauses:
        raise HTTPException(status_code=400, detail="该合同没有条款，无法审查")

    # 未配置 API Key 提前拦截（call_json 内部会抛 RuntimeError，但节点会吞掉它）
    if not settings.deepseek_api_key:
        raise HTTPException(
            status_code=503,
            detail="LLM 服务未配置：请在项目根目录的 .env 文件里填写 DEEPSEEK_API_KEY 后重启服务",
        )

    state = review_service.build_state(contract_id, clauses)

    start = time.perf_counter()
    try:
        # thread_id 必须传（否则 checkpointer 抛 ValueError）；用 uuid 保证每次独立会话
        config = {"configurable": {"thread_id": f"{contract_id}-{uuid.uuid4().hex}"}}
        result = get_graph().invoke(state, config=config)
    except RuntimeError as exc:  # 例如 LLM 相关 RuntimeError
        logger.exception("合同 %s 审查失败（RuntimeError）", contract_id)
        raise HTTPException(status_code=503, detail=f"审查失败：{exc}") from exc
    except Exception as exc:  # noqa: BLE001  未预期异常记日志后转 500
        logger.exception("合同 %s 审查失败", contract_id)
        raise HTTPException(status_code=500, detail="审查过程中发生内部错误") from exc

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    fields = result.get("fields") or {}
    errors = result.get("errors") or []

    review_service.persist_result(db, contract_id, result)

    risk_rows = db.scalars(
        select(RiskItem).where(RiskItem.contract_id == contract_id).order_by(RiskItem.id)
    ).all()

    return AnalyzeResponse(
        contract_id=contract_id,
        risk_count=len(risk_rows),
        fields=fields,
        risks=[RiskItemOut.model_validate(r) for r in risk_rows],
        errors=errors,
        elapsed_ms=elapsed_ms,
    )


@router.post(
    "/{contract_id}/review",
    status_code=202,
    summary="提交异步审查（后台执行）",
)
def submit_review(
    contract_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """提交审查任务，立即返回 task_id，后台执行。

    防重复原则：数据库是唯一事实来源，Redis 锁只是防并发的加速手段。
    - 先查 DB 有无 pending/running 任务，有则直接返回它；
    - 再抢锁（Redis 正常时防并发竞态）；
    - Redis 不可用时降级为无锁，但只在 DB 确认无活跃任务后才新建。
    """
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="合同不存在")

    clauses = db.scalars(
        select(Clause).where(Clause.contract_id == contract_id).order_by(Clause.id)
    ).all()
    if not clauses:
        raise HTTPException(status_code=400, detail="该合同没有条款，无法审查")

    if not settings.deepseek_api_key:
        raise HTTPException(
            status_code=503,
            detail="LLM 服务未配置：请在项目根目录的 .env 文件里填写 DEEPSEEK_API_KEY 后重启服务",
        )

    # 1. DB 优先：先查有没有正在跑的任务
    existing = _find_active_task(db, contract_id)
    if existing is not None:
        return {"task_id": existing.id, "status": existing.status}

    # 2. 没有活跃任务，尝试抢锁
    lock_key = redis_client.key("lock", "contract", contract_id)
    lock_result = _acquire_lock(lock_key, _REVIEW_LOCK_TTL)

    if lock_result is False:
        # 锁被占用：别的请求可能刚建好任务，再查一次 DB
        existing = _find_active_task(db, contract_id)
        if existing is not None:
            return {"task_id": existing.id, "status": existing.status}
        raise HTTPException(status_code=409, detail="该合同正在审查中，请稍后查看")

    # True（抢到锁）或 None（Redis 不可用，DB 已确认无活跃任务）→ 新建
    task = ReviewTask(
        contract_id=contract_id, status="pending", progress=0, stage="排队中"
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    background_tasks.add_task(run_review, task.id, contract_id)

    return {"task_id": task.id, "status": "pending"}


@router.get("/{contract_id}/report", summary="审查报告（带缓存）")
def get_report(contract_id: int, db: Session = Depends(get_db)) -> dict:
    """先查 Redis 缓存；未命中则组装合同 + 条款 + 风险 + 建议并写缓存。"""
    contract = db.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="合同不存在")

    report_key = redis_client.key("report", contract_id)

    cached, redis_ok = _get_report_cache(report_key)
    if cached is not None:
        return cached

    clauses = db.scalars(
        select(Clause).where(Clause.contract_id == contract_id).order_by(Clause.id)
    ).all()
    risks = db.scalars(
        select(RiskItem).where(RiskItem.contract_id == contract_id).order_by(RiskItem.id)
    ).all()

    report = {
        "contract_id": contract_id,
        "filename": contract.filename,
        "status": contract.status,
        "risk_count": len(risks),
        "clauses": [ClauseOut.model_validate(c).model_dump() for c in clauses],
        "risks": [RiskItemOut.model_validate(r).model_dump() for r in risks],
    }

    # 读缓存时 Redis 已失败，就跳过写缓存，避免同一次请求白等第二次超时
    if redis_ok:
        _set_report_cache(report_key, report)

    return report


# ------------------------------------------------------------------ 内部辅助


def _acquire_lock(lock_key: str, ttl: int) -> bool | None:
    """抢分布式锁，三态返回：
    - True  = 抢到锁
    - False = 锁被别的请求持有
    - None  = Redis 不可用（降级）
    """
    try:
        return bool(redis_client.get_redis().set(lock_key, "1", nx=True, ex=ttl))
    except Exception as exc:  # noqa: BLE001  Redis 不可用
        logger.warning("Redis 不可用，锁降级为无锁模式：%s", exc)
        return None


def _find_active_task(db: Session, contract_id: int):
    """查该合同最近一个 pending / running 任务。"""
    return db.scalars(
        select(ReviewTask)
        .where(
            ReviewTask.contract_id == contract_id,
            ReviewTask.status.in_(("pending", "running")),
        )
        .order_by(ReviewTask.id.desc())
    ).first()


def _get_report_cache(report_key: str) -> tuple[dict | None, bool]:
    """读报告缓存，返回 (缓存值或 None, Redis 是否可用)。

    Redis 挂了或未命中时缓存值为 None；第二个值标记 Redis 是否可用，
    供 get_report 判断是否还要写缓存，避免同一次请求白等第二次超时。
    """
    try:
        raw = redis_client.get_redis().get(report_key)
        if raw:
            return json.loads(raw), True
        return None, True
    except Exception as exc:  # noqa: BLE001
        logger.warning("读报告缓存失败：%s", exc)
        return None, False


def _set_report_cache(report_key: str, report: dict) -> None:
    """写报告缓存，Redis 挂了只 warning。"""
    try:
        redis_client.get_redis().set(
            report_key,
            json.dumps(report, ensure_ascii=False),
            ex=settings.cache_ttl_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("写报告缓存失败：%s", exc)
