from __future__ import annotations

from typing import Any, TypedDict

from mini_agent.types import Message, Observation, PermissionDecision, ToolCall, ToolResult


class AgentState(TypedDict):
    user_input: str
    messages: list[Message]
    observations: list[Observation]
    tool_call: ToolCall | None
    permission_decision: PermissionDecision | None
    approval_result: dict[str, Any] | None
    tool_result: ToolResult | None
    observation: Observation | None
    final_answer: str | None
    step: int
    max_steps: int
    errors: list[dict[str, Any]]
