"""职责：Redis 连接管理 + key 前缀拼接。

对外函数都要安全降级：Redis 挂了绝不能让接口 500。

连接参数说明（redis-py 8.x）：
socket_connect_timeout / socket_timeout / retry / health_check_interval 这些参数
都通过 ConnectionPool 的 **connection_kwargs 落到 Connection 层生效，
因此统一在 ConnectionPool.from_url 里设置。
"""

from __future__ import annotations

import logging

from redis import ConnectionPool, Redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from app.config import settings

logger = logging.getLogger(__name__)

# 模块级连接池：decode_responses=True，读出来的直接是 str
_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    """懒加载连接池。"""
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=0.3,   # 连接超时：Redis 挂掉时快速失败
            socket_timeout=0.3,           # 读写超时
            max_connections=20,           # 最大连接数
            health_check_interval=30,     # 每 30 秒健康检查
            retry=Retry(NoBackoff(), 0),  # 显式关闭重试，连接错误不重试
        )
    return _pool


def get_redis() -> Redis:
    """获取一个 Redis 客户端（复用连接池）。"""
    return Redis(connection_pool=_get_pool())


def ping_redis() -> bool:
    """探测 Redis 是否可用；异常返回 False，不抛。"""
    try:
        return bool(get_redis().ping())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis 不可用：%s", exc)
        return False


def key(*parts) -> str:
    """统一拼接带前缀的 key：key("task", 12) -> "cg:task:12"。"""
    return ":".join([settings.redis_key_prefix, *[str(p) for p in parts]])
