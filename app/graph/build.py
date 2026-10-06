"""LangGraph 조립. 체크포인터는 쓰지 않는다 — 세션은 Redis 단순 키(app.chat.session)가 맡는다."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.graph import nodes
from app.graph.state import ChatState


def build_graph():
    g = StateGraph(ChatState)
    g.add_node("guard", nodes.guard)
    g.add_node("interpret", nodes.interpret)
    g.add_node("execute", nodes.execute)
    g.add_edge(START, "guard")
    g.add_conditional_edges("guard", nodes.after_guard, {"execute": "execute", "interpret": "interpret", "end": END})
    g.add_conditional_edges("interpret", nodes.after_interpret, {"execute": "execute", "end": END})
    g.add_edge("execute", END)
    return g.compile()
