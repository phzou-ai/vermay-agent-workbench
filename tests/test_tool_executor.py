from pydantic import Field

from vermay_agent.tool_executor import ToolExecutor
from vermay_agent.tool_registry import ToolRegistry
from vermay_agent.tooling import ToolArgs, structured_tool
from vermay_agent.types import ToolCall


class EchoArgs(ToolArgs):
    value: str = Field(description="Value to echo.")


class EmptyArgs(ToolArgs):
    pass


def test_executor_returns_successful_tool_result():
    registry = ToolRegistry()
    registry.register(
        structured_tool(
            func=lambda value: {"value": value},
            name="echo",
            description="Echo value.",
            args_schema=EchoArgs,
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
        structured_tool(
            func=fail,
            name="fail",
            description="Failing tool.",
            args_schema=EmptyArgs,
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
