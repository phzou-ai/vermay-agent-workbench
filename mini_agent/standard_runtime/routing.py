from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage

from .state import StandardAgentState


def latest_ai_message(messages: list[BaseMessage]) -> AIMessage | None:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message
    return None


def route_after_model(state: StandardAgentState) -> str:
    if state.get("final_answer") is not None:
        return "final"

    ai_message = latest_ai_message(state.get("messages", []))
    if ai_message is not None and ai_message.tool_calls:
        return "tool_calls"

    return "final"


def route_loop_limit(state: StandardAgentState) -> str:
    if state["loop_index"] > state["max_loops"]:
        return "max_loops"
    return "continue"
