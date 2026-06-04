from vermay_agent.permission import PermissionGate
from vermay_agent.tool_registry import ToolRegistry
from vermay_agent.tooling import ToolArgs, structured_tool
from vermay_agent.types import ToolCall


class EmptyArgs(ToolArgs):
    pass


def make_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        structured_tool(
            func=lambda: "ok",
            name="safe_tool",
            description="Safe test tool.",
            args_schema=EmptyArgs,
            dangerous=False,
        )
    )
    registry.register(
        structured_tool(
            func=lambda: "not executed",
            name="dangerous_tool",
            description="Dangerous test tool.",
            args_schema=EmptyArgs,
            dangerous=True,
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
