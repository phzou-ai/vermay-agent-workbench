from mini_agent.permission import PermissionGate
from mini_agent.tool_registry import ToolRegistry
from mini_agent.types import ToolCall, ToolSpec


def make_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="safe_tool",
            description="Safe test tool.",
            parameters={"type": "object", "properties": {}},
            dangerous=False,
            func=lambda: "ok",
        )
    )
    registry.register(
        ToolSpec(
            name="dangerous_tool",
            description="Dangerous test tool.",
            parameters={"type": "object", "properties": {}},
            dangerous=True,
            func=lambda: "not executed",
        )
    )
    return registry


def test_safe_tool_is_allowed_without_approval():
    decision = PermissionGate(make_registry()).check(ToolCall(name="safe_tool"))

    assert decision.allowed is True
    assert decision.requires_approval is False
    assert decision.reason == "safe tool"


def test_dangerous_tool_requires_approval():
    decision = PermissionGate(make_registry()).check(ToolCall(name="dangerous_tool"))

    assert decision.allowed is False
    assert decision.requires_approval is True
    assert "dangerous_tool" in decision.reason
