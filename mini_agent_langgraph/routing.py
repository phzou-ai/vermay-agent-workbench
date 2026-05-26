from __future__ import annotations

from .state import AgentState


def route_after_model(state: AgentState) -> str:
    if state.get("final_answer") is not None:
        return "final"
    if state.get("tool_call") is not None:
        return "tool_call"
    return "final"


def route_after_permission(state: AgentState) -> str:
    decision = state.get("permission_decision")
    if decision is None:
        return "denied"
    if decision.requires_approval:
        return "approval_required"
    if decision.allowed:
        return "allowed"
    return "denied"


def route_after_approval(state: AgentState) -> str:
    approval = state.get("approval_result") or {}
    if approval.get("approved") is True:
        return "approved"
    return "rejected"


def route_after_step(state: AgentState) -> str:
    if state["step"] > state["max_steps"]:
        return "max_steps"
    return "continue"
