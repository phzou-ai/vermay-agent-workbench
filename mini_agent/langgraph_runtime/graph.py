from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import (
    GraphComponents,
    approval_required_node,
    build_context_node,
    call_model_node,
    check_permission_node,
    execute_tool_node,
    handle_observation_node,
    increment_step_node,
    reject_tool_node,
)
from .routing import route_after_approval, route_after_model, route_after_permission, route_after_step
from .state import AgentState


def build_graph(components: GraphComponents, checkpointer=None):
    graph = StateGraph(AgentState)

    graph.add_node("build_context", build_context_node(components))
    graph.add_node("call_model", call_model_node(components))
    graph.add_node("check_permission", check_permission_node(components))
    graph.add_node("approval_required", approval_required_node(components))
    graph.add_node("reject_tool", reject_tool_node(components))
    graph.add_node("execute_tool", execute_tool_node(components))
    graph.add_node("handle_observation", handle_observation_node(components))
    graph.add_node("increment_step", increment_step_node(components))

    graph.add_edge(START, "build_context")
    graph.add_edge("build_context", "call_model")
    graph.add_conditional_edges(
        "call_model",
        route_after_model,
        {
            "final": END,
            "tool_call": "check_permission",
        },
    )
    graph.add_conditional_edges(
        "check_permission",
        route_after_permission,
        {
            "approval_required": "approval_required",
            "denied": "reject_tool",
            "allowed": "execute_tool",
        },
    )
    graph.add_conditional_edges(
        "approval_required",
        route_after_approval,
        {
            "approved": "execute_tool",
            "rejected": "reject_tool",
        },
    )
    graph.add_edge("reject_tool", END)
    graph.add_edge("execute_tool", "handle_observation")
    graph.add_edge("handle_observation", "increment_step")
    graph.add_conditional_edges(
        "increment_step",
        route_after_step,
        {
            "continue": "build_context",
            "max_steps": END,
        },
    )

    return graph.compile(checkpointer=checkpointer)
