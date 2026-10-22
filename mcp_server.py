"""合同卫士 MCP Server：把合同检索 / 查询能力封装成标准化工具。

独立进程，不依赖 FastAPI、不依赖 Redis；向量不可用时自动降级纯 BM25。
用法：
    python mcp_server.py            # stdio 传输，供 Claude Desktop / Cursor 等客户端
    python scripts/test_mcp.py      # 用官方客户端自测 4 个工具

注意：环境里是 mcp 2.x，MCPServer 取代了旧版的 FastMCP。
"""

from __future__ import annotations

import json
import logging
import time

from sqlalchemy import func, select

from app.db import Base, SessionLocal, engine
from app.models import Clause, Contract, ContractProfile, RiskItem
from app.services import retriever
from mcp.server.mcpserver import MCPServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("contractguard.mcp")

server = MCPServer("contractguard", title="合同卫士", version="0.1.0")


def _log_call(tool: str, elapsed_ms: int, extra: str = "") -> None:
    """统一打点：工具名 + 耗时 + 附加信息（参数/返回条数）。"""
    logger.info("tool=%s elapsed_ms=%d %s", tool, elapsed_ms, extra)


@server.tool()
def list_contracts() -> list[dict]:
    """列出数据库中所有合同的概要信息。

    返回每个合同的 id、文件名、状态、条款数量和风险数量。
    当不知道有哪些合同可以查询时，先调用这个工具获取合同列表。
    """
    start = time.perf_counter()
    try:
        with SessionLocal() as db:
            contracts = db.scalars(select(Contract).order_by(Contract.id)).all()
            result = []
            for c in contracts:
                clause_count = db.scalar(
                    select(func.count()).select_from(Clause).where(Clause.contract_id == c.id)
                ) or 0
                risk_count = db.scalar(
                    select(func.count()).select_from(RiskItem).where(RiskItem.contract_id == c.id)
                ) or 0
                result.append(
                    {
                        "contract_id": c.id,
                        "filename": c.filename,
                        "status": c.status,
                        "clause_count": clause_count,
                        "risk_count": risk_count,
                    }
                )
        _log_call("list_contracts", int((time.perf_counter() - start) * 1000), f"count={len(result)}")
        return result
    except Exception as exc:  # noqa: BLE001  工具内部兜底，不抛异常
        logger.exception("list_contracts 失败")
        return [{"error": str(exc)}]


@server.tool()
def get_contract_meta(contract_id: int) -> dict:
    """查询指定合同的基本信息与已抽取的关键字段。

    contract_id 是必填的整数。返回文件名、状态、页数、字数，以及已抽取的字段
    （如甲方、乙方、合同金额、付款账期、违约金比例、争议管辖地等）。
    若字段尚未抽取，fields 返回空 dict，且 fields_available 为 false。
    """
    start = time.perf_counter()
    try:
        with SessionLocal() as db:
            c = db.get(Contract, contract_id)
            if c is None:
                return {"error": f"合同 {contract_id} 不存在"}

            profile = db.scalar(
                select(ContractProfile).where(ContractProfile.contract_id == contract_id)
            )
            fields: dict = {}
            if profile and profile.payload:
                try:
                    fields = json.loads(profile.payload)
                except Exception:  # noqa: BLE001  payload 损坏则按空处理
                    fields = {}

            result = {
                "contract_id": c.id,
                "filename": c.filename,
                "status": c.status,
                "page_count": c.page_count,
                "char_count": c.char_count,
                "fields": fields,
                "fields_available": bool(fields),
            }
        _log_call("get_contract_meta", int((time.perf_counter() - start) * 1000), f"id={contract_id}")
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("get_contract_meta 失败")
        return {"error": str(exc)}


@server.tool()
def search_clause(contract_id: int, query: str, top_k: int = 5) -> list[dict]:
    """在指定合同内按语义和关键词混合检索相关条款。

    contract_id 是合同 id；query 是要检索的问题或关键词，例如「违约金怎么约定」；
    top_k 控制返回条数（默认 5）。返回每条条款的编号、标题、正文和相关性得分。
    若合同尚未建立向量索引，会自动降级为关键词检索，结果里标 degraded=true。
    """
    start = time.perf_counter()
    try:
        q = (query or "").strip()
        if not q:
            return [{"error": "query 不能为空"}]

        with SessionLocal() as db:
            if db.get(Contract, contract_id) is None:
                return [{"error": f"合同 {contract_id} 不存在"}]

            clauses = retriever.hybrid_search(db, contract_id, q, top_k=top_k)

            # 该合同是否没有任何 embedding（未建索引 → 向量路降级为纯 BM25）
            has_embedding = db.scalar(
                select(func.count())
                .select_from(Clause)
                .where(Clause.contract_id == contract_id, Clause.embedding.isnot(None))
            ) or 0
            degraded = has_embedding == 0

            result = []
            for c in clauses:
                item = {
                    "clause_id": c["clause_id"],
                    "clause_no": c["clause_no"],
                    "title": c["title"],
                    "content": c["content"],
                    "score": c["score"],
                }
                if degraded:
                    item["degraded"] = True
                result.append(item)

        _log_call(
            "search_clause",
            int((time.perf_counter() - start) * 1000),
            f"id={contract_id} top_k={top_k} count={len(result)}",
        )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("search_clause 失败")
        return [{"error": str(exc)}]


@server.tool()
def get_clause(contract_id: int, clause_no: str) -> dict:
    """按条款编号精确获取指定合同中的某一条条款。

    clause_no 形如「第六条」「第十条」。返回条款编号、标题、正文和页码。
    若该条款不存在，返回 error 字段说明。
    """
    start = time.perf_counter()
    try:
        with SessionLocal() as db:
            if db.get(Contract, contract_id) is None:
                return {"error": f"合同 {contract_id} 不存在"}

            clause = db.scalar(
                select(Clause).where(
                    Clause.contract_id == contract_id,
                    Clause.clause_no == clause_no,
                )
            )
            if clause is None:
                return {"error": "未找到该条款"}

            result = {
                "clause_id": clause.id,
                "clause_no": clause.clause_no,
                "title": clause.title,
                "content": clause.content,
                "page_no": clause.page_no,
            }
        _log_call("get_clause", int((time.perf_counter() - start) * 1000), f"id={contract_id} no={clause_no}")
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("get_clause 失败")
        return {"error": str(exc)}


if __name__ == "__main__":
    # 独立进程启动时确保表存在（create_all 幂等，只创建缺失的新表，如 contract_profile）
    Base.metadata.create_all(bind=engine)
    server.run()
