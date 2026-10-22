"""职责：LangGraph 节点——字段抽取 + 风险识别（纯计算，不碰数据库）。

硬性约束：
- 禁止访问数据库、禁止 import Session、禁止出现 ORM 对象；
- 禁止 print，统一用 logging；
- prompt 文件用 pathlib + utf-8 读取，并做模块级缓存。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

from app.graph.state import FieldExtraction, RiskJudgement, State
from app.services.llm import call_json
from app.services.risk_rules import screen_candidates

logger = logging.getLogger(__name__)

# prompts 目录：app/prompts
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# 并发与超限约束：并发 3 个、候选组合最多 15 个（见阶段 2 约束）
_MAX_WORKERS = 3
_MAX_COMBOS = 15


@lru_cache(maxsize=None)
def _load_prompt(name: str) -> str:
    """读取提示词模板（utf-8），模块级缓存，避免每次调用都读盘。"""
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def extract_fields_node(state: State) -> dict:
    """整篇合同调一次 LLM，抽取关键字段。"""
    clauses = state.get("clauses", [])
    # 把所有条款 content 用换行拼成整篇合同文本
    full_text = "\n".join(c.get("content", "") or "" for c in clauses)
    if not full_text.strip():
        logger.warning("合同正文为空，跳过字段抽取")
        return {"fields": {}, "errors": ["字段抽取失败：合同正文为空"]}

    system_prompt = _load_prompt("extract_fields.txt")
    try:
        result = call_json(system_prompt, full_text, FieldExtraction)
        return {"fields": result.model_dump()}
    except Exception as exc:  # noqa: BLE001  单节点失败不抛异常，记入 errors
        logger.exception("字段抽取失败：%s", exc)
        return {"fields": {}, "errors": [f"字段抽取失败：{exc}"]}


def detect_risks_node(state: State) -> dict:
    """粗筛候选 → 展开成 (条款, 风险类型) 组合 → 并发精判。"""
    clauses = state.get("clauses", [])
    errors: list[str] = []

    # 1. 规则粗筛，得到候选条款及其命中类型
    candidates = screen_candidates(clauses)

    # 2. 展开成 (clause, risk_type) 组合，一条条款命中多类型就拆成多个组合
    combos: list[tuple[dict, str]] = [
        (clause, risk_type)
        for clause, risk_types in candidates
        for risk_type in risk_types
    ]

    # 3. 最多取前 15 个，超出丢弃并记一条 error
    if len(combos) > _MAX_COMBOS:
        overflow = len(combos) - _MAX_COMBOS
        errors.append(f"候选组合 {len(combos)} 个超过上限 {_MAX_COMBOS}，丢弃 {overflow} 个")
        combos = combos[:_MAX_COMBOS]

    system_template = _load_prompt("detect_risk.txt")

    def _judge(combo: tuple[dict, str]) -> RiskJudgement:
        """单个组合精判：把占位符替换成该组合的 risk_type 后调 LLM。"""
        clause, risk_type = combo
        user_prompt = (
            f"条款编号：{clause.get('clause_no', '')}\n"
            f"条款标题：{clause.get('title', '')}\n"
            f"条款原文：\n{clause.get('content', '')}"
        )
        system_prompt = system_template.replace("__CANDIDATE_TYPES__", risk_type)
        return call_json(system_prompt, user_prompt, RiskJudgement)

    risks: list[dict] = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        future_map = {pool.submit(_judge, combo): combo for combo in combos}
        for future in as_completed(future_map):
            clause, risk_type = future_map[future]
            clause_no = clause.get("clause_no", "")
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001  单个组合失败不影响其它
                logger.warning(
                    "条款 %s 风险类型 %s 判定失败：%s", clause_no, risk_type, exc
                )
                errors.append(f"条款 {clause_no} 风险类型 {risk_type} 判定失败：{exc}")
                continue

            if not result.is_risk:
                continue

            # risk_type 直接用组合里的值（候选只有一个，避免模型自创类型）
            risks.append(
                {
                    "clause_id": clause.get("clause_id"),
                    "risk_type": risk_type,
                    "risk_level": result.risk_level,
                    "reason": result.reason,
                    "suggestion": result.suggestion,
                    "confidence": result.confidence,
                }
            )

    return {"risks": risks, "errors": errors}
