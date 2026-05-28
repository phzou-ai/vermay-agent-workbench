from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from mini_agent.permission import PermissionGate
from mini_agent.tool_registry import ToolRegistry
from mini_agent.types import ToolCall, ToolSpec
from mini_agent.langgraph_runtime.toolnode_adapter import (
    extract_tool_messages,
    tool_call_to_ai_message,
    tool_spec_to_structured_tool,
)


class ToolNodeAdapterTestState(TypedDict):
    messages: Annotated[list, add_messages]


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="echo",
            description="Echo a value.",
            parameters={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            },
            dangerous=False,
            func=lambda value: {"value": value},
        )
    )
    registry.register(
        ToolSpec(
            name="dangerous",
            description="Dangerous placeholder.",
            parameters={"type": "object", "properties": {}},
            dangerous=True,
            func=lambda: {"executed": True},
        )
    )
    registry.register(
        ToolSpec(
            name="fail",
            description="Failing tool.",
            parameters={"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
            dangerous=False,
            func=lambda value: (_ for _ in ()).throw(ValueError("bad value")),
        )
    )
    return registry


def build_toolnode_graph(registry: ToolRegistry, tool_names: list[str]):
    tools = [tool_spec_to_structured_tool(registry.get(name)) for name in tool_names]
    graph = StateGraph(ToolNodeAdapterTestState)
    graph.add_node("tools", ToolNode(tools, handle_tool_errors=True))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    return graph.compile()


def run_toolnode(registry: ToolRegistry, tool_call: ToolCall) -> ToolMessage:
    graph = build_toolnode_graph(registry, [tool_call.name])
    output = graph.invoke({"messages": [tool_call_to_ai_message(tool_call, call_id="call-adapter-test")]})
    tool_messages = extract_tool_messages(output["messages"])
    if not tool_messages:
        raise AssertionError("ToolNode did not return a ToolMessage")
    return tool_messages[-1]


def test_tool_call_to_ai_message_adapts_current_tool_call_shape():
    message = tool_call_to_ai_message(ToolCall(name="echo", arguments={"value": "hello"}), call_id="call-1")

    assert isinstance(message, AIMessage)
    assert message.tool_calls == [
        {"name": "echo", "args": {"value": "hello"}, "id": "call-1", "type": "tool_call"}
    ]


def test_toolnode_executes_safe_tool_and_returns_tool_message():
    message = run_toolnode(build_registry(), ToolCall(name="echo", arguments={"value": "hello"}))

    assert isinstance(message, ToolMessage)
    assert message.name == "echo"
    assert message.tool_call_id == "call-adapter-test"
    assert message.status == "success"
    assert message.content == '{"value": "hello"}'


def test_toolnode_keeps_tool_result_inside_messages_state():
    registry = build_registry()
    graph = build_toolnode_graph(registry, ["echo"])

    output = graph.invoke(
        {"messages": [tool_call_to_ai_message(ToolCall(name="echo", arguments={"value": "hello"}), call_id="call-1")]}
    )

    assert len(output["messages"]) == 2
    assert isinstance(output["messages"][0], AIMessage)
    assert isinstance(output["messages"][1], ToolMessage)
    assert output["messages"][1].content == '{"value": "hello"}'


def test_toolnode_handles_tool_error_as_tool_message():
    message = run_toolnode(build_registry(), ToolCall(name="fail", arguments={"value": "bad"}))

    assert message.name == "fail"
    assert message.status == "error"
    assert "ValueError('bad value')" in message.content


def test_toolnode_would_execute_dangerous_tool_without_external_permission_gate():
    registry = build_registry()
    decision = PermissionGate(registry).check(ToolCall(name="dangerous"))

    message = run_toolnode(registry, ToolCall(name="dangerous"))

    assert decision.requires_approval is True
    assert message.status == "success"
    assert message.content == '{"executed": true}'
