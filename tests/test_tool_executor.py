from mini_agent.tool_executor import ToolExecutor
from mini_agent.tool_registry import ToolRegistry
from mini_agent.types import ToolCall, ToolSpec


def test_executor_returns_successful_tool_result():
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="echo",
            description="Echo value.",
            parameters={"type": "object", "properties": {"value": {"type": "string"}}},
            dangerous=False,
            func=lambda value: {"value": value},
        )
    )

    result = ToolExecutor(registry).execute(ToolCall(name="echo", arguments={"value": "hello"}))

    assert result.name == "echo"
    assert result.ok is True
    assert result.output == {"value": "hello"}
    assert result.error is None


def test_executor_normalizes_tool_failure():
    registry = ToolRegistry()

    def fail() -> None:
        raise RuntimeError("boom")

    registry.register(
        ToolSpec(
            name="fail",
            description="Failing tool.",
            parameters={"type": "object", "properties": {}},
            dangerous=False,
            func=fail,
        )
    )

    result = ToolExecutor(registry).execute(ToolCall(name="fail"))

    assert result.name == "fail"
    assert result.ok is False
    assert result.output is None
    assert result.error == "RuntimeError: boom"


def test_executor_normalizes_unknown_tool_failure():
    result = ToolExecutor(ToolRegistry()).execute(ToolCall(name="missing"))

    assert result.name == "missing"
    assert result.ok is False
    assert result.error == "KeyError: 'unknown tool: missing'"
