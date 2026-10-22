"""LLM 调用封装：DeepSeek ChatOpenAI + 结构化输出 + JSON 退化 + 打点。

设计取舍（见项目文档）：
- LLM 输出必须是结构化 JSON，用 Pydantic 强校验，下游才好写库、展示、评测；
- 优先用 with_structured_output，失败则退化为「只输出 JSON」再 model_validate；
- 单条失败向上抛，由调用方决定跳过还是终止，本模块不做静默吞异常。
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

# 匹配 ```json ... ``` 或 ``` ... ``` 代码块
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def get_chat_model(timeout: int = 30) -> ChatOpenAI:
    """构造 DeepSeek 的 ChatOpenAI 实例。

    timeout 默认 30s：analyze 是同步长请求，必须限制单次调用时长，
    避免最坏情况把 HTTP 请求挂几分钟导致浏览器/网关断开。
    """
    if not settings.deepseek_api_key:
        raise RuntimeError(
            "未配置 DeepSeek API Key，请在项目根目录的 .env 文件中填写 "
            "DEEPSEEK_API_KEY 后重启服务"
        )
    return ChatOpenAI(
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key,
        temperature=0,
        timeout=timeout,
        max_retries=2,
    )


def _strip_json(text: str) -> str:
    """从模型输出里剥离出纯 JSON 文本。"""
    text = (text or "").strip()
    match = _JSON_FENCE.search(text)
    if match:
        return match.group(1).strip()
    # 兜底：截取第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _extract_usage(msg: Any) -> tuple[int | None, int | None]:
    """从 AIMessage 里取 prompt / completion token 数，拿不到返回 (None, None)。

    注意：结构化输出路径通常拿不到 usage，这里不为了拿 usage 去绕
    include_raw 的版本兼容坑，拿不到就记 None。
    """
    prompt: int | None = None
    completion: int | None = None

    usage_metadata = getattr(msg, "usage_metadata", None)
    if isinstance(usage_metadata, dict):
        prompt = usage_metadata.get("input_tokens")
        completion = usage_metadata.get("output_tokens")

    response_metadata = getattr(msg, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage") or {}
    if isinstance(token_usage, dict):
        if prompt is None:
            prompt = token_usage.get("prompt_tokens")
        if completion is None:
            completion = token_usage.get("completion_tokens")

    return prompt, completion


def call_json(
    system_prompt: str,
    user_prompt: str,
    schema: type[BaseModel],
    timeout: int = 30,
) -> BaseModel:
    """让 LLM 输出符合 schema 的 JSON 对象。

    流程：
    1. 优先用 with_structured_output(schema)；
    2. 失败则退化为「只输出 JSON」+ 剥离代码块 + schema.model_validate，重试 1 次；
    3. 打点记录耗时与 token 用量（结构化输出拿不到 token 就记 None）。
    """
    model = get_chat_model(timeout=timeout)
    start = time.perf_counter()

    # ---- 路径一：结构化输出 ----
    try:
        structured = model.with_structured_output(schema)
        result = structured.invoke([("system", system_prompt), ("user", user_prompt)])
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "LLM 结构化输出成功 schema=%s elapsed_ms=%d prompt_tokens=None completion_tokens=None",
            schema.__name__,
            elapsed_ms,
        )
        return result
    except Exception as exc:  # noqa: BLE001  退化为 JSON 模式
        logger.warning("结构化输出失败，退化为 JSON 模式：%s", exc)

    # ---- 路径二：JSON 模式 + 重试 1 次 ----
    json_user = (
        user_prompt
        + "\n\n请只输出一个 JSON 对象，不要包含任何解释、Markdown 代码块或额外文本。"
    )
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            msg = model.invoke([("system", system_prompt), ("user", json_user)])
            content = msg.content
            if not isinstance(content, str):
                content = str(content)
            data = json.loads(_strip_json(content))
            result = schema.model_validate(data)
            prompt_tokens, completion_tokens = _extract_usage(msg)
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            logger.info(
                "LLM JSON 输出成功 schema=%s elapsed_ms=%d prompt_tokens=%s completion_tokens=%s",
                schema.__name__,
                elapsed_ms,
                prompt_tokens,
                completion_tokens,
            )
            return result
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("JSON 解析失败（第 %d/2 次）：%s", attempt + 1, exc)

    raise RuntimeError(f"LLM 输出解析失败，schema={schema.__name__}：{last_exc}")
