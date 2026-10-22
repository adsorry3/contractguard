"""职责：任务状态查询 + SSE 进度流。"""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.services import task_store

router = APIRouter(prefix="/api/tasks", tags=["任务"])

_POLL_INTERVAL = 0.5        # SSE 轮询间隔（秒）
_MAX_STREAM_SECONDS = 600   # SSE 最长 10 分钟


@router.get("/{task_id}", summary="查询任务状态")
def get_task_status(task_id: int) -> dict:
    """查询任务进度；不存在返回 404。"""
    task = task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/{task_id}/stream", summary="任务进度 SSE 流")
async def stream_task(task_id: int):
    """每 500ms 推一次任务状态；done/failed 结束；10 分钟兜底。"""

    async def event_generator():
        deadline = time.monotonic() + _MAX_STREAM_SECONDS
        while True:
            task = await asyncio.to_thread(task_store.get_task, task_id)
            if task is None:
                yield {
                    "event": "error",
                    "data": json.dumps({"detail": "任务不存在"}, ensure_ascii=False),
                }
                break

            yield {"data": json.dumps(task, ensure_ascii=False)}

            if task.get("status") in ("done", "failed"):
                break
            if time.monotonic() > deadline:
                yield {
                    "event": "timeout",
                    "data": json.dumps({"detail": "流超时"}, ensure_ascii=False),
                }
                break
            await asyncio.sleep(_POLL_INTERVAL)

    return EventSourceResponse(event_generator())
