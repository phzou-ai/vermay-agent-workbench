from __future__ import annotations

"""Small project value types retained for model-adapter and legacy harness bridges.

The active LangGraph runtime uses LangChain messages and ToolNode for graph
execution. `Message`, `ModelResponse`, and `ToolCall` remain useful at the
model-adapter and permission boundaries. `ToolResult` and `Observation` are
kept for the archived hands-on harness path and focused compatibility tests.
"""

from dataclasses import dataclass, field
from typing import Any, Literal


MessageRole = Literal["system", "user", "assistant", "tool"]


@dataclass
class Message:
    role: MessageRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    id: str | None = None


@dataclass
class ToolResult:
    name: str
    ok: bool
    output: Any = None
    error: str | None = None


@dataclass
class Observation:
    tool_name: str
    content: str
    ok: bool


@dataclass
class PermissionDecision:
    allowed: bool
    requires_approval: bool
    reason: str


@dataclass
class ModelResponse:
    content: str
    tool_call: ToolCall | None = None

    @property
    def has_tool_call(self) -> bool:
        return self.tool_call is not None
