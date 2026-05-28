from __future__ import annotations

from typing import Any

from mini_agent.types import Observation, PermissionDecision, ToolCall, ToolResult


def tool_call_payload(tool_call: ToolCall | None) -> dict[str, Any] | None:
    if tool_call is None:
        return None
    return {"name": tool_call.name, "arguments": tool_call.arguments}


def permission_payload(decision: PermissionDecision | None) -> dict[str, Any] | None:
    if decision is None:
        return None
    return {
        "allowed": decision.allowed,
        "requires_approval": decision.requires_approval,
        "reason": decision.reason,
    }


def tool_result_payload(result: ToolResult | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        "name": result.name,
        "ok": result.ok,
        "output": result.output,
        "error": result.error,
    }


def observation_payload(observation: Observation | None) -> dict[str, Any] | None:
    if observation is None:
        return None
    return {
        "tool_name": observation.tool_name,
        "content": observation.content,
        "ok": observation.ok,
    }
