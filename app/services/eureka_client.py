"""Eureka 服务注册客户端：让 AI-SERVICE 能被 Java 侧通过服务名发现。

Eureka 的 REST 协议只有三个请求，直接用 httpx 实现，不引入第三方 SDK：
    1. 注册   POST   {eureka_url}/eureka/apps/AI-SERVICE
    2. 心跳   PUT    {eureka_url}/eureka/apps/AI-SERVICE/{instanceId}
    3. 注销   DELETE {eureka_url}/eureka/apps/AI-SERVICE/{instanceId}

设计要点：
    - 模块级单例，start() 注册一次 + 起后台守护线程发心跳，stop() 优雅注销
    - 所有网络异常只打 warning，绝不抛出，保证 Eureka 不可用时服务照常可用
    - 心跳返回 404（实例不存在）时自动重新注册，实现断线自愈
"""

from __future__ import annotations

import logging
import threading

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

APP_NAME = "AI-SERVICE"
# instanceId 用连字符拼接，避免冒号在 URL 里被编码成 %3A（不同 Eureka 版本解码行为不一致）
INSTANCE_ID = f"ai-service-{settings.ai_service_port}"

# 单次请求超时（秒）：Eureka 没开时最多等这么久，不能卡住启动
_TIMEOUT = 3.0
# 心跳间隔（秒），与注册体里 leaseInfo.renewalIntervalInSecs 保持一致
_HEARTBEAT_INTERVAL = 30
# 心跳成功每满 N 次打一条 INFO，其余打 DEBUG，避免刷屏
_HEARTBEAT_LOG_EVERY = 10


def _build_instance_body() -> dict:
    """构造 Eureka 注册请求体（InstanceInfo）。"""
    port = settings.ai_service_port
    return {
        "instance": {
            "instanceId": INSTANCE_ID,
            "hostName": "127.0.0.1",
            "app": APP_NAME,
            "ipAddr": "127.0.0.1",
            "vipAddress": "ai-service",
            "secureVipAddress": "ai-service",
            "status": "UP",
            "port": {"$": port, "@enabled": "true"},
            "securePort": {"$": 443, "@enabled": "false"},
            "dataCenterInfo": {
                "@class": "com.netflix.appinfo.InstanceInfo$DefaultDataCenterInfo",
                "name": "MyOwn",
            },
            "leaseInfo": {
                "renewalIntervalInSecs": _HEARTBEAT_INTERVAL,
                "durationInSecs": 90,
            },
            "healthCheckUrl": f"http://127.0.0.1:{port}/health",
            "statusPageUrl": f"http://127.0.0.1:{port}/docs",
            "homePageUrl": f"http://127.0.0.1:{port}/",
        }
    }


class EurekaClient:
    """Eureka 客户端单例：负责注册、心跳、注销。"""

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._renew_ok_count = 0

    def _apps_url(self, suffix: str = "") -> str:
        """拼接 Eureka apps 相关 URL。"""
        base = settings.eureka_url.rstrip("/")
        return f"{base}/eureka/apps/{APP_NAME}{suffix}"

    def _register(self) -> bool:
        """注册一次。成功返回 True，失败返回 False（只打 warning，不抛异常）。"""
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        try:
            resp = httpx.post(
                self._apps_url(),
                json=_build_instance_body(),
                headers=headers,
                timeout=_TIMEOUT,
            )
        except Exception as exc:  # noqa: BLE001  网络异常统一捕获
            logger.warning("Eureka 注册失败（服务仍可正常使用）：%s", exc)
            return False

        if resp.status_code in (200, 204):
            logger.info("Eureka 注册成功 app=%s instance=%s", APP_NAME, INSTANCE_ID)
            return True
        logger.warning(
            "Eureka 注册失败（服务仍可正常使用）：HTTP %s %s",
            resp.status_code,
            resp.text[:200],
        )
        return False

    def _renew(self) -> None:
        """发一次心跳。200 续约成功；404 实例不存在，自动重新注册。"""
        try:
            resp = httpx.put(self._apps_url(f"/{INSTANCE_ID}"), timeout=_TIMEOUT)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Eureka 心跳异常 app=%s：%s", APP_NAME, exc)
            return

        if resp.status_code == 200:
            self._renew_ok_count += 1
            if self._renew_ok_count % _HEARTBEAT_LOG_EVERY == 0:
                logger.info(
                    "Eureka 心跳成功 app=%s instance=%s（第 %d 次续约）",
                    APP_NAME,
                    INSTANCE_ID,
                    self._renew_ok_count,
                )
            else:
                logger.debug(
                    "Eureka 心跳成功 app=%s instance=%s", APP_NAME, INSTANCE_ID
                )
        elif resp.status_code == 404:
            logger.warning(
                "Eureka 心跳返回 404，实例不存在，自动重新注册 app=%s", APP_NAME
            )
            self._register()
        else:
            logger.warning(
                "Eureka 心跳异常 app=%s：HTTP %s", APP_NAME, resp.status_code
            )

    def _heartbeat_loop(self) -> None:
        """后台守护线程：每隔 _HEARTBEAT_INTERVAL 秒发一次心跳，直到收到停止信号。"""
        logger.info("Eureka 心跳线程已启动，间隔 %d 秒", _HEARTBEAT_INTERVAL)
        while not self._stop_event.wait(_HEARTBEAT_INTERVAL):
            self._renew()
        logger.info("Eureka 心跳线程已停止")

    def start(self) -> None:
        """注册一次并启动心跳线程。任何失败都不影响服务启动。"""
        if not settings.eureka_enabled:
            logger.info("Eureka 注册已禁用（eureka_enabled=false），跳过")
            return

        self._renew_ok_count = 0
        # 注册失败只打 warning；心跳线程照常启动，等 Eureka 恢复后靠 404 触发重新注册
        self._register()

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._heartbeat_loop, name="eureka-heartbeat", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """停止心跳线程并主动注销，让面板上立刻消失（不等租约过期）。"""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=_TIMEOUT)

        if not settings.eureka_enabled:
            return

        try:
            resp = httpx.delete(self._apps_url(f"/{INSTANCE_ID}"), timeout=_TIMEOUT)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Eureka 注销失败：%s", exc)
            return

        if resp.status_code in (200, 204):
            logger.info("Eureka 注销成功 app=%s instance=%s", APP_NAME, INSTANCE_ID)
        else:
            logger.warning("Eureka 注销失败：HTTP %s", resp.status_code)


# 模块级单例
eureka_client = EurekaClient()
