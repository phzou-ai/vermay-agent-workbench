from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import StandardGraphComponents, call_model_node
from .routing import route_after_model
from .state import StandardAgentState


def build_standard_graph(components: StandardGraphComponents, checkpointer=None):
    graph = StateGraph(StandardAgentState)
    graph.add_node("call_model", call_model_node(components))

    graph.add_edge(START, "call_model")
    graph.add_conditional_edges(
        "call_model",
        route_after_model,
        {
            "final": END,
            "tool_calls": END,
        },
    )

    return graph.compile(checkpointer=checkpointer)
