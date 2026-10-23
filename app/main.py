"""FastAPI 入口：初始化数据库、注册路由、挂载静态目录。"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.api import ai, contracts, tasks
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.services.eureka_client import eureka_client
from app.services.redis_client import ping_redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def _mark_zombie_tasks_failed() -> None:
    """把上次服务退出时遗留的 pending/running 任务置为 failed。"""
    from sqlalchemy import update

    from app.models import ReviewTask

    with SessionLocal() as db:
        db.execute(
            update(ReviewTask)
            .where(ReviewTask.status.in_(("pending", "running")))
            .values(status="failed", error_text="服务重启，任务中断")
        )
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时建表、建目录；关闭时打印日志。"""
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path("static").mkdir(exist_ok=True)

    import app.models  # noqa: F401  确保模型被注册到 Base.metadata

    Base.metadata.create_all(bind=engine)
    logger.info("数据库已就绪：%s", settings.database_url)

    # 清理僵尸任务：上次服务退出时仍 pending/running 的任务置为 failed
    _mark_zombie_tasks_failed()

    # 探测 Redis，失败只 warning 不阻止启动
    if not ping_redis():
        logger.warning("Redis 不可用，任务进度与报告缓存将降级为数据库兜底")

    # 注册到 Eureka：放到独立线程跑，避免同步 HTTP 阻塞事件循环；失败不影响启动
    try:
        await asyncio.to_thread(eureka_client.start)
    except Exception:  # noqa: BLE001  内部已捕获，这里兜底
        logger.warning("Eureka 注册启动异常，服务仍可正常使用", exc_info=True)

    logger.info("服务启动完成，访问 http://127.0.0.1:8000/docs")

    yield

    # 优雅注销：主动 DELETE，让 Eureka 面板上立刻消失，不等租约过期
    try:
        await asyncio.to_thread(eureka_client.stop)
    except Exception:  # noqa: BLE001  内部已捕获，这里兜底
        logger.warning("Eureka 注销异常", exc_info=True)

    logger.info("服务已关闭")


app = FastAPI(
    title=settings.app_name,
    description="企业合同智能审查平台",
    version="0.1.0",
    lifespan=lifespan,
)

if Path("static").exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(contracts.router)
app.include_router(tasks.router)
app.include_router(ai.router)


@app.get("/health", tags=["系统"])
def health() -> dict:
    """健康检查：确认服务和数据库都正常。"""
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))

    tables = sorted(inspect(engine).get_table_names())
    return {
        "status": "ok",
        "app": settings.app_name,
        "database": settings.database_url.split("://", 1)[0],
        "tables": tables,
        "table_count": len(tables),
    }


@app.get("/", tags=["系统"])
def index():
    """首页：有前端就返回前端，没有就返回接口信息。"""
    page = Path("static/index.html")
    if page.exists():
        return FileResponse(page)
    return {
        "message": "ContractGuard API",
        "docs": "/docs",
        "health": "/health",
    }
