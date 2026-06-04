from __future__ import annotations

from .tool_registry import ToolRegistry
from .types import PermissionDecision, ToolCall


class PermissionGate:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def check(self, tool_call: ToolCall) -> PermissionDecision:
        if self.registry.is_dangerous(tool_call.name):
            return PermissionDecision(
                allowed=False,
                requires_approval=True,
                reason=f"tool '{tool_call.name}' is marked dangerous",
            )
        return PermissionDecision(allowed=True, requires_approval=False, reason="safe tool")
