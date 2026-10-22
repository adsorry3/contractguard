"""MCP Server 自测：用官方客户端 stdio 连接 mcp_server.py，调用 4 个工具并断言。

用法（项目根目录下）：
    python scripts/test_mcp.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp_server.py"


def extract(res) -> dict | list:
    """从 CallToolResult 提取结构化结果。

    MCP 2.x 会把 list 返回值拆成多个 content 块，完整结果在 structured_content 里，
    这里优先取它，回退到遍历 content 解析。
    """
    sc = getattr(res, "structured_content", None)
    if isinstance(sc, dict) and "result" in sc:
        return sc["result"]
    parts = [json.loads(c.text) for c in res.content]
    return parts[0] if len(parts) == 1 else parts


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER)],
        cwd=str(ROOT),
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. 工具列表
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print("[1] list_tools:", names)
            assert len(tools.tools) == 4, f"期望 4 个工具，实际 {len(tools.tools)}"

            # 2. list_contracts
            r = await session.call_tool("list_contracts", {})
            data = extract(r)
            print("[2] list_contracts 共", len(data), "个合同")
            assert isinstance(data, list) and len(data) >= 1

            # 3. search_clause（命中违约金条款）
            r = await session.call_tool(
                "search_clause", {"contract_id": 3, "query": "违约金", "top_k": 3}
            )
            data = extract(r)
            dump = json.dumps(data, ensure_ascii=False)
            print("[3] search_clause:", dump[:300])
            assert isinstance(data, list) and len(data) >= 1 and "违约金" in dump

            # 4. get_clause（精确取一条）
            r = await session.call_tool("get_clause", {"contract_id": 3, "clause_no": "第六条"})
            data = extract(r)
            print("[4] get_clause:", json.dumps(data, ensure_ascii=False))
            assert isinstance(data, dict) and "error" not in data and data.get("content")

            # 5. 不存在的合同 → error，不崩
            r = await session.call_tool("search_clause", {"contract_id": 999999, "query": "违约金"})
            data = extract(r)
            print("[5] search_clause(999999):", json.dumps(data, ensure_ascii=False))
            assert "error" in json.dumps(data, ensure_ascii=False)

            # 6. 不存在的条款 → error
            r = await session.call_tool("get_clause", {"contract_id": 3, "clause_no": "第九十九条"})
            data = extract(r)
            print("[6] get_clause(不存在条款):", json.dumps(data, ensure_ascii=False))
            assert "error" in data

    print("\n全部断言通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
