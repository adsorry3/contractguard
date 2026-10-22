"""职责：任务状态读写（Redis 优先，DB 兜底）。

Redis 存任务进度（读写快），review_task 表做持久化兜底。
所有 Redis 操作 try/except 降级：Redis 挂了只用数据库，绝不 500。
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.config import settings
from app.db import SessionLocal
from app.models import ReviewTask
from app.services import redis_client

logger = logging.getLogger(__name__)


def set_task(
    task_id: int, *, status: str, progress: int, stage: str, error_text: str = ""
) -> None:
    """写任务状态：先写数据库兜底，再写 Redis（可降级）。"""
    # 1. 数据库兜底（永远要成功）
    with SessionLocal() as db:
        task = db.get(ReviewTask, task_id)
        if task is None:
            logger.warning("任务 %s 不存在，无法更新状态", task_id)
        else:
            task.status = status
            task.progress = progress
            task.stage = stage
            task.error_text = error_text
            if status == "running" and task.started_at is None:
                task.started_at = datetime.now()
            if status in ("done", "failed") and task.finished_at is None:
                task.finished_at = datetime.now()
            db.commit()

    # 2. Redis（可降级）
    try:
        r = redis_client.get_redis()
        hash_key = redis_client.key("task", task_id)
        r.hset(
            hash_key,
            mapping={
                "task_id": str(task_id),
                "status": status,
                "progress": str(progress),
                "stage": stage,
                "error_text": error_text,
            },
        )
        r.expire(hash_key, settings.task_ttl_seconds)
    except Exception as exc:  # noqa: BLE001  Redis 挂了降级用数据库
        logger.warning("写 Redis 任务状态失败，降级用数据库：%s", exc)


def get_task(task_id: int) -> dict | None:
    """读任务状态：先 Redis，未命中或挂了回查数据库。"""
    # 1. 先查 Redis
    try:
        r = redis_client.get_redis()
        data = r.hgetall(redis_client.key("task", task_id))
        if data:
            return {
                "task_id": int(data.get("task_id", task_id)),
                "status": data.get("status", ""),
                "progress": int(data.get("progress", 0) or 0),
                "stage": data.get("stage", ""),
                "error_text": data.get("error_text", ""),
            }
    except Exception as exc:  # noqa: BLE001  Redis 挂了降级查数据库
        logger.warning("读 Redis 任务状态失败，降级查数据库：%s", exc)

    # 2. Redis 未命中（比如超过 TTL）或挂了，回查数据库
    with SessionLocal() as db:
        task = db.get(ReviewTask, task_id)
        if task is None:
            return None
        return {
            "task_id": task.id,
            "status": task.status,
            "progress": task.progress,
            "stage": task.stage,
            "error_text": task.error_text,
        }
