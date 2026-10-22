"""职责：调用硅基流动 Embedding 接口（BAAI/bge-m3），批量向量化文本。

直接用 httpx POST，不用 langchain 的 embedding 封装，少一层黑盒。
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# 单次请求超时（秒）：批量 embedding 通常 1-2 秒，30 秒给足余量
_TIMEOUT = 30.0


def embed_texts(texts: list[str]) -> list[list[float]]:
    """把一批文本转成向量，返回顺序与输入一致。

    - 一次请求批量发完，带 30 秒超时 + 1 次重试；
    - SILICONFLOW_API_KEY 为空时抛中文 RuntimeError。
    """
    if not settings.siliconflow_api_key:
        raise RuntimeError(
            "未配置 SILICONFLOW_API_KEY，请在项目根目录的 .env 文件中填写后重启服务"
        )
    if not texts:
        return []

    url = settings.siliconflow_base_url.rstrip("/") + "/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.siliconflow_api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": settings.embedding_model, "input": texts}

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            # 按 index 排序，保证向量顺序和 input 一一对应
            items = sorted(data.get("data", []), key=lambda x: x.get("index", 0))
            vectors = [item["embedding"] for item in items]
            if len(vectors) != len(texts):
                raise RuntimeError(
                    f"Embedding 返回条数不一致：期望 {len(texts)}，实际 {len(vectors)}"
                )
            return vectors
        except Exception as exc:  # noqa: BLE001  统一捕获后重试，最后一次抛出
            last_exc = exc
            logger.warning("Embedding 请求失败（第 %d/2 次）：%s", attempt + 1, exc)

    raise RuntimeError(f"Embedding 调用失败：{last_exc}")
