"""职责：条款向量化 + 混合检索（向量余弦 + BM25，RRF 融合）。

检索单元是 clause 表的条款，合同通常几十条以内，全量暴力计算是毫秒级，
不需要向量数据库。中文没有分词器，BM25 用字符 2-gram 切分。
"""

from __future__ import annotations

import json
import logging

import numpy as np
from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Clause
from app.services.embedding import embed_texts

logger = logging.getLogger(__name__)

# RRF 融合常量
_RRF_K = 60
# 向量路 / 关键词路各自先取 top 20，再融合
_CANDIDATE_K = 20

# 第一层拒答门控阈值：向量 top1 余弦低于此值直接拒答（不调 LLM）。
# 实测（samples/sample_contract.docx，BAAI/bge-m3）：
#   - 相关（"逾期要赔多少钱" vs 违约金条款）  ≈ 0.73
#   - 无关（"今天北京天气怎么样"）           ≈ 0.31
#   0.45 取两者中点，验收时校准：
#   若「仲裁机构」这类应拒答问题的 top1 余弦 > 0.45，说明阈值偏低，需上调。
VECTOR_REJECT_THRESHOLD = 0.45


def _text_to_bigram(text: str) -> list[str]:
    """字符 2-gram 切分："违约金" -> ["违约", "约金"]，长度 < 2 返回原字符。"""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) < 2:
        return [text]
    return [text[i : i + 2] for i in range(len(text) - 1)]


def build_index(db: Session, contract_id: int) -> int:
    """给该合同所有 clause 批量向量化并写回 embedding，幂等。

    - 已有 embedding 的条款跳过；
    - 返回本次新向量化的条数。
    """
    clauses = db.scalars(
        select(Clause).where(Clause.contract_id == contract_id).order_by(Clause.id)
    ).all()
    if not clauses:
        return 0

    todo = [c for c in clauses if not c.embedding]
    if not todo:
        return 0

    # 向量化优先用正文，正文为空退回标题/编号
    texts = [(c.content or c.title or c.clause_no).strip() for c in todo]
    vectors = embed_texts(texts)

    for clause, vec in zip(todo, vectors):
        clause.embedding = json.dumps(vec)
    db.commit()

    logger.info("合同 %s 完成向量化 %d/%d 条", contract_id, len(todo), len(clauses))
    return len(todo)


def _load_clauses(db: Session, contract_id: int) -> list[Clause]:
    return db.scalars(
        select(Clause).where(Clause.contract_id == contract_id).order_by(Clause.id)
    ).all()


def _load_embeddings(clauses: list[Clause]) -> tuple[list[int], np.ndarray]:
    """从 clause 里解析 embedding，返回 (clause_id 列表, 二维数组)。

    无 embedding 或解析失败的条款被跳过（向量路降级，BM25 仍可用）。
    """
    ids: list[int] = []
    vecs: list[list[float]] = []
    for c in clauses:
        if not c.embedding:
            continue
        try:
            vec = json.loads(c.embedding)
            if len(vec) == settings.embedding_dim:
                ids.append(c.id)
                vecs.append(vec)
            else:
                logger.warning("条款 %s embedding 维度异常 %d，跳过", c.id, len(vec))
        except Exception:  # noqa: BLE001
            logger.warning("条款 %s embedding 解析失败，跳过", c.id)
    if not vecs:
        return [], np.empty((0, settings.embedding_dim))
    return ids, np.array(vecs)


def _cosine_similarity(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """查询向量与矩阵逐行余弦相似度。"""
    if matrix.shape[0] == 0:
        return np.empty(0)
    q = query_vec / (np.linalg.norm(query_vec) + 1e-9)
    m = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
    return m @ q


def vector_top1_similarity(db: Session, contract_id: int, query: str) -> float | None:
    """计算 query 与该合同最相似条款的余弦值，用于第一层拒答门控。

    - 返回 None 表示没有可用向量（全部无 embedding 或计算失败）；
    - 同时把 top1 分数打到日志，方便验收时校准阈值。
    """
    clauses = _load_clauses(db, contract_id)
    ids, matrix = _load_embeddings(clauses)
    if not ids or matrix.shape[0] == 0:
        return None

    try:
        qv = np.array(embed_texts([query])[0])
        sims = _cosine_similarity(qv, matrix)
        top1 = float(sims.max())
        logger.info(
            "合同 %s 问答向量 top1 余弦=%.4f query=%s",
            contract_id,
            top1,
            query[:40],
        )
        return top1
    except Exception as exc:  # noqa: BLE001
        logger.warning("向量 top1 计算失败：%s", exc)
        return None


def hybrid_search(
    db: Session, contract_id: int, query: str, top_k: int = 5
) -> list[dict]:
    """混合检索：向量余弦 + BM25（字符 2-gram），RRF 融合，返回 top_k。

    每项含 {clause_id, clause_no, title, content, score}。
    - 若某条款无 embedding，向量路跳过它，BM25 仍可用（降级）。
    """
    clauses = _load_clauses(db, contract_id)
    if not clauses:
        return []

    clause_by_id = {c.id: c for c in clauses}

    # ---- 向量路：余弦 top 20 ----
    vector_rank: dict[int, int] = {}
    ids, matrix = _load_embeddings(clauses)
    if ids and matrix.shape[0] > 0:
        try:
            qv = np.array(embed_texts([query])[0])
            sims = _cosine_similarity(qv, matrix)
            order = np.argsort(-sims)[:_CANDIDATE_K]
            for rank, pos in enumerate(order):
                vector_rank[ids[pos]] = rank
        except Exception as exc:  # noqa: BLE001
            logger.warning("向量检索失败，降级为纯 BM25：%s", exc)

    # ---- 关键词路：BM25 字符 2-gram，top 20 ----
    bm25_rank: dict[int, int] = {}
    corpus = [_text_to_bigram(c.content or c.title or "") for c in clauses]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(_text_to_bigram(query))
    order = np.argsort(-scores)[:_CANDIDATE_K]
    for rank, pos in enumerate(order):
        if scores[pos] > 0:  # 只保留命中的条款
            bm25_rank[clauses[pos].id] = rank

    # ---- RRF 融合 ----
    rrf: dict[int, float] = {}
    for cid, rank in vector_rank.items():
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (_RRF_K + rank)
    for cid, rank in bm25_rank.items():
        rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (_RRF_K + rank)

    ranked = sorted(rrf.items(), key=lambda kv: kv[1], reverse=True)[:top_k]

    result = []
    for cid, score in ranked:
        c = clause_by_id[cid]
        result.append(
            {
                "clause_id": c.id,
                "clause_no": c.clause_no,
                "title": c.title,
                "content": c.content,
                "score": round(score, 6),
            }
        )
    return result
