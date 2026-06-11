"""LangGraph StateGraph 构建。"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.graph.nodes import (
    analysis_node,
    chitchat_node,
    decision_node,
    intent_node,
    observation_node,
    pattern_node,
    planner_node,
    route_after_decision,
    route_after_intent,
    route_after_validate,
    route_analysis_dispatch,
    sql_execute_node,
    sql_generate_node,
    sql_validate_node,
    summarize_node,
    tool_executor_node,
    tool_selector_node,
    volatility_node,
    volume_price_node,
)
from app.graph.state import AgentState


def build_graph() -> StateGraph:
    """构建 LangGraph 状态图。

    图结构：
        START → intent → (conditional)
          ├─ sql_generate → sql_execute → sql_validate → (conditional)
          │                                                  ├─ retry → sql_execute (循环)
          │                                                  ├─ query_ok → dispatch → (conditional)
          │                                                  └─ fail → summarize
          └─ sql_execute → sql_validate → ...
                                    dispatch:
                                      ├─ query → summarize
                                      ├─ analysis → basic_analysis → summarize
                                      ├─ pattern → pattern_analysis → summarize
                                      ├─ volume_price → volume_price_analysis → summarize
                                      └─ volatility → volatility_analysis → summarize
        summarize → END
    """
    graph = StateGraph(AgentState)

    # 注册节点
    graph.add_node("intent", intent_node)
    graph.add_node("planner", planner_node)
    graph.add_node("tool_selector", tool_selector_node)
    graph.add_node("tool_executor", tool_executor_node)
    graph.add_node("observation", observation_node)
    graph.add_node("decision", decision_node)
    graph.add_node("chitchat", chitchat_node)
    graph.add_node("sql_generate", sql_generate_node)
    graph.add_node("sql_execute", sql_execute_node)
    graph.add_node("sql_validate", sql_validate_node)
    graph.add_node("analysis_dispatch", lambda state: {})  # 虚拟分发节点
    graph.add_node("basic_analysis", analysis_node)
    graph.add_node("pattern_analysis", pattern_node)
    graph.add_node("volume_price_analysis", volume_price_node)
    graph.add_node("volatility_analysis", volatility_node)
    graph.add_node("summarize", summarize_node)

    # 入口
    graph.set_entry_point("intent")

    # intent → chitchat / planner
    graph.add_conditional_edges("intent", route_after_intent, {
        "chitchat": "chitchat",
        "planner": "planner",
    })

    # planner → tool_selector
    graph.add_edge("planner", "tool_selector")

    # tool_selector → tool_executor
    graph.add_edge("tool_selector", "tool_executor")

    # tool_executor → observation
    graph.add_edge("tool_executor", "observation")

    # observation → decision
    graph.add_edge("observation", "decision")

    # decision → summarize / tool_selector / sql_generate
    graph.add_conditional_edges("decision", route_after_decision, {
        "summarize": "summarize",
        "tool_selector": "tool_selector",
        "sql_generate": "sql_generate",
    })

    # sql_generate → sql_execute
    graph.add_edge("sql_generate", "sql_execute")

    # sql_execute → sql_validate（始终先验证）
    graph.add_edge("sql_execute", "sql_validate")

    # sql_validate → 重试 / 分析分发 / 总结
    graph.add_conditional_edges("sql_validate", route_after_validate, {
        "sql_execute": "sql_execute",       # 重试：回到执行节点
        "analysis_dispatch": "analysis_dispatch",  # 成功：进入分析分发
        "summarize": "summarize",           # 失败/空结果：直接总结
    })

    # analysis_dispatch → 具体分析节点
    graph.add_conditional_edges("analysis_dispatch", route_analysis_dispatch, {
        "query_done": "summarize",
        "basic_analysis": "basic_analysis",
        "pattern_analysis": "pattern_analysis",
        "volume_price_analysis": "volume_price_analysis",
        "volatility_analysis": "volatility_analysis",
    })

    # chitchat → summarize
    graph.add_edge("chitchat", "summarize")

    # 各分析节点 → 总结
    for node_name in ("basic_analysis", "pattern_analysis", "volume_price_analysis", "volatility_analysis"):
        graph.add_edge(node_name, "summarize")

    # 总结 → 结束
    graph.add_edge("summarize", END)

    return graph.compile()


_COMPILED_GRAPH = None


def get_graph():
    """获取编译后的图（单例）。"""
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is None:
        _COMPILED_GRAPH = build_graph()
    return _COMPILED_GRAPH
