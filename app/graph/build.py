"""职责：构建 LangGraph 审查流程图（START → extract_fields → detect_risks → END）。"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

# 检查点：优先 InMemorySaver，旧版本回退 MemorySaver
try:
    from langgraph.checkpoint.memory import InMemorySaver
except ImportError:  # 兼容旧版本命名
    from langgraph.checkpoint.memory import MemorySaver as InMemorySaver

from app.graph.nodes import detect_risks_node, extract_fields_node
from app.graph.state import State

# 模块级单例，避免每次请求都重新编译图
_graph = None


def build_graph():
    """构建并编译审查流程图，返回编译后的图对象。"""
    graph = StateGraph(State)
    graph.add_node("extract_fields", extract_fields_node)
    graph.add_node("detect_risks", detect_risks_node)
    graph.add_edge(START, "extract_fields")
    graph.add_edge("extract_fields", "detect_risks")
    graph.add_edge("detect_risks", END)
    return graph.compile(checkpointer=InMemorySaver())


def get_graph():
    """获取编译后的图单例。"""
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
