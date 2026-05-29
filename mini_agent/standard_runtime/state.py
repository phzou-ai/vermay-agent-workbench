from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph.message import add_messages


class StandardAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    approval: dict[str, Any] | None
    final_answer: str | None
    loop_index: int
    max_loops: int
    errors: list[dict[str, Any]]


def build_initial_state(
    user_input: str,
    *,
    system_prompt: str | None = None,
    max_loops: int = 5,
) -> StandardAgentState:
    messages: list[BaseMessage] = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    messages.append(HumanMessage(content=user_input))
    return {
        "messages": messages,
        "approval": None,
        "final_answer": None,
        "loop_index": 1,
        "max_loops": max_loops,
        "errors": [],
    }
