"""职责：合同问答（RAG 生成层）。

流程：第一层门控（向量 top1 余弦）→ 混合检索 top5 → 拼 prompt 调 LLM
→ 第二层门控（answered=false 转标准拒答话术）→ citations 映射回真实条款。
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.services import retriever
from app.services.llm import call_json

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# 引用来源里展示的条款内容片段长度
_SNIPPET_LEN = 50
# 拒答话术里「它约定的是 Y」的 Y 长度（更短更精炼）
_REFUSAL_LEN = 20


@lru_cache(maxsize=None)
def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


class QAResult(BaseModel):
    """问答 LLM 输出结构。"""

    answered: bool = True
    answer: str = ""
    citations: list[int] = []


def answer_question(db: Session, contract_id: int, question: str) -> dict:
    """基于合同原文回答问题，返回 {answer, citations, latency_ms}。"""
    start = time.perf_counter()

    def _refused(msg: str) -> dict:
        return {
            "answer": msg,
            "citations": [],
            "latency_ms": int((time.perf_counter() - start) * 1000),
        }

    # ---- 第一层门控：向量 top1 余弦 < 阈值 → 直接拒答，不调 LLM ----
    top1_score = retriever.vector_top1_similarity(db, contract_id, question)
    if top1_score is not None and top1_score < retriever.VECTOR_REJECT_THRESHOLD:
        logger.info("合同 %s 问答第一层门控拒答 top1_cos=%.3f", contract_id, top1_score)
        return _refused("提供的条款中未找到与问题相关的内容。")

    # ---- 混合检索 top5 ----
    clauses = retriever.hybrid_search(db, contract_id, question, top_k=5)
    if not clauses:
        return _refused("提供的条款中未找到相关内容。")

    # ---- 拼 prompt，记录 编号 -> 条款 映射（编号是喂给模型的顺序，不是 clause_no）----
    index_map: dict[int, dict] = {}
    user_parts: list[str] = []
    for i, c in enumerate(clauses, start=1):
        index_map[i] = c
        user_parts.append(f"[{i}] 第{c['clause_no']}条 {c['title']}\n{c['content']}")
    user_prompt = "\n\n".join(user_parts) + f"\n\n问题：{question}"

    system_prompt = _load_prompt("qa.txt")

    try:
        result = call_json(system_prompt, user_prompt, QAResult)
    except Exception as exc:  # noqa: BLE001
        logger.exception("合同 %s 问答 LLM 调用失败", contract_id)
        raise RuntimeError(f"问答生成失败：{exc}") from exc

    # ---- 第二层门控：模型判断不能回答 → 标准拒答话术 ----
    if not result.answered:
        # 拒答话术与 citations 由同一处生成，保证正文提到的条款与引用一致
        answer, citations = _build_refusal(clauses, question)
    else:
        answer = result.answer or ""
        citations = _map_citations(result.citations, index_map)

    return {
        "answer": answer,
        "citations": citations,
        "latency_ms": int((time.perf_counter() - start) * 1000),
    }


def _extract_keyword(question: str) -> str:
    """从问句里提取短关键词，用于拒答话术（不引分词库，纯字符串规则）。

    去掉疑问语气词/标点、常见问句前缀，再截断到 12 字；空则回退「该问题」。
    """
    q = (question or "").strip()

    # 1. 去掉结尾的疑问语气词和标点
    q = q.rstrip("？?。.!！ ")
    for _ in range(3):
        if q.endswith(("吗", "呢", "啊", "么", "吧")):
            q = q[:-1].rstrip("？?。.!！ ")
        else:
            break

    # 2. 去掉开头的常见问句前缀（长词在前，避免误切）
    prefixes = (
        "请问一下", "请问", "这份合同", "本合同", "合同的",
        "合同中有没有", "合同中是否有", "合同是否约定了", "合同是否",
        "合同有没有", "合同约定了", "合同约定", "合同里", "合同",
        "有没有", "是否",
    )
    changed = True
    while changed:
        changed = False
        for p in prefixes:
            if q.startswith(p):
                q = q[len(p):].lstrip(" ，,:：、的")
                changed = True
                break

    # 3. 截断到 12 字
    if len(q) > 12:
        q = q[:12] + "…"

    q = q.strip(" ，,:：、")
    return q or "该问题"


def _shorten(text: str, limit: int) -> str:
    """压缩文本：去换行、超长截断加省略号。"""
    text = (text or "").strip().replace("\n", " ")
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def _strip_leading_title(content: str, clause_no: str, title: str) -> str:
    """去掉正文首行的「编号 + 标题」重复（与前端 clauseContent 同逻辑）。"""
    lines = (content or "").split("\n")
    if not lines:
        return ""
    first = lines[0].strip()
    no = (clause_no or "").strip()
    title = (title or "").strip()
    if no and first.startswith(no):
        rest = first[len(no):].lstrip(" :：、.．").strip()
        if not title or rest == title or rest.startswith(title):
            return "\n".join(lines[1:]).strip()
    return (content or "").strip()


def _build_refusal(clauses: list[dict], question: str) -> tuple[str, list[dict]]:
    """生成拒答话术，返回 (话术文本, citations)。

    - 话术里提到的「最接近条款」必须进入 citations（index=1），文本末尾标 [1]；
    - 无可用条款时 citations 为空，话术里也不提任何条款。
    """
    keyword = _extract_keyword(question)

    if not clauses:
        return "提供的条款中未找到相关内容。", []

    top = clauses[0]
    # 该条款到底约定了什么：去掉正文首行标题后取一段精炼内容
    body = _strip_leading_title(top["content"], top["clause_no"], top["title"])
    snippet = _shorten(body, _REFUSAL_LEN)

    answer = (
        f"提供的条款中没有关于「{keyword}」的约定。"
        f"最接近的是{top['clause_no']}（{top['title']}），"
        f"但它约定的是：{snippet}，未涉及{keyword}[1]"
    )

    citation = {
        "index": 1,
        "clause_id": top["clause_id"],
        "clause_no": top["clause_no"],
        "title": top["title"],
        "snippet": _shorten(body, _SNIPPET_LEN),
    }
    return answer, [citation]


def _map_citations(citations: list[int], index_map: dict[int, dict]) -> list[dict]:
    """把模型返回的 [1,2] 编号映射回真实条款。

    [1] 指的是喂给模型的第 1 条（index_map 的 key），不是「第一条」。
    """
    result = []
    for idx in citations:
        clause = index_map.get(idx)
        if clause is None:
            continue
        result.append(
            {
                "index": idx,
                "clause_id": clause["clause_id"],
                "clause_no": clause["clause_no"],
                "title": clause["title"],
                "snippet": _shorten(clause["content"] or "", _SNIPPET_LEN),
            }
        )
    return result
