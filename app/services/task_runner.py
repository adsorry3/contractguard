"""职责：后台审查任务执行器（不接收请求线程的 Session，自己建）。"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.db import SessionLocal
from app.graph.build import get_graph
from app.models import Clause
from app.services import redis_client, review_service, task_store

logger = logging.getLogger(__name__)


def run_review(task_id: int, contract_id: int) -> None:
    """后台执行审查：读条款 → 跑图 → 落库，全程自建 Session，最后释放锁。"""
    lock_key = redis_client.key("lock", "contract", contract_id)

    try:
        task_store.set_task(task_id, status="running", progress=5, stage="开始审查")

        # 读条款
        with SessionLocal() as db:
            clauses = db.scalars(
                select(Clause)
                .where(Clause.contract_id == contract_id)
                .order_by(Clause.id)
            ).all()

        if not clauses:
            task_store.set_task(
                task_id,
                status="failed",
                progress=0,
                stage="失败",
                error_text="该合同没有条款，无法审查",
            )
            return

        state = review_service.build_state(contract_id, clauses)
        # 手动合并各节点的增量结果
        result: dict = {"fields": {}, "risks": [], "errors": []}

        graph = get_graph()
        # thread_id 必须传（否则 checkpointer 抛 ValueError）
        config = {"configurable": {"thread_id": f"{contract_id}-{task_id}"}}

        for chunk in graph.stream(state, config=config, stream_mode="updates"):
            if "extract_fields" in chunk:
                update = chunk["extract_fields"]
                if "fields" in update:
                    result["fields"] = update["fields"]
                if update.get("errors"):
                    result.setdefault("errors", []).extend(update["errors"])
                task_store.set_task(
                    task_id, status="running", progress=50, stage="字段抽取完成"
                )
            if "detect_risks" in chunk:
                update = chunk["detect_risks"]
                if "risks" in update:
                    result["risks"] = update["risks"]
                if update.get("errors"):
                    result.setdefault("errors", []).extend(update["errors"])
                task_store.set_task(
                    task_id, status="running", progress=90, stage="风险识别完成"
                )

        # 落库
        with SessionLocal() as db:
            review_service.persist_result(db, contract_id, result)

        task_store.set_task(task_id, status="done", progress=100, stage="审查完成")

    except Exception as exc:  # noqa: BLE001
        logger.exception("任务 %s 执行失败", task_id)
        try:
            task_store.set_task(
                task_id, status="failed", progress=0, stage="失败", error_text=str(exc)
            )
        except Exception:  # noqa: BLE001  写失败状态也失败，不再处理
            logger.exception("写失败状态也失败，任务 %s", task_id)
    finally:
        _release_lock(lock_key)


def _release_lock(lock_key: str) -> None:
    """释放分布式锁；Redis 挂了只 warning。"""
    try:
        redis_client.get_redis().delete(lock_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("释放锁失败：%s", exc)
