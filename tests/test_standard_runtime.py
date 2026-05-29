from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from mini_agent.model_clients import OllamaModelClient
from mini_agent.permission import PermissionGate
from mini_agent.progress import ProgressReporter
from mini_agent.standard_runtime import StandardOllamaModelClient
from mini_agent.standard_runtime.graph import build_standard_graph
from mini_agent.standard_runtime.nodes import StandardGraphComponents
from mini_agent.standard_runtime.routing import (
    latest_ai_message,
    route_after_approval,
    route_after_model,
    route_after_permission,
    route_loop_limit,
)
from mini_agent.standard_runtime.runner import StandardLangGraphAgentRuntime
from mini_agent.standard_runtime.state import build_initial_state
from mini_agent.standard_runtime.tools import tool_spec_to_structured_tool
from mini_agent.tool_registry import ToolRegistry
from mini_agent.trace import TraceLogger
from mini_agent.types import ToolSpec


class FakeStandardModel:
    def __init__(self, responses: AIMessage | list[AIMessage]) -> None:
        self.responses = responses if isinstance(responses, list) else [responses]
        self.calls = []

    def invoke(self, messages, tools):
        self.calls.append((messages, tools))
        return self.responses.pop(0)


class FakeProjectModelClient:
    def __init__(self, response) -> None:
        self.response = response
        self.calls = []

    def invoke(self, messages, tools):
        self.calls.append((messages, tools))
        return self.response


def test_standard_initial_state_uses_langchain_messages():
    state = build_initial_state("hello", system_prompt="system prompt", max_loops=3)

    assert isinstance(state["messages"][0], SystemMessage)
    assert isinstance(state["messages"][1], HumanMessage)
    assert state["messages"][0].content == "system prompt"
    assert state["messages"][1].content == "hello"
    assert state["loop_index"] == 1
    assert state["max_loops"] == 3
    assert state["final_answer"] is None


def test_standard_routing_detects_ai_message_tool_calls():
    state = build_initial_state("weather")
    state["messages"].append(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "weather_forecast",
                    "args": {"location": "Shanghai"},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        )
    )

    assert latest_ai_message(state["messages"]) is state["messages"][-1]
    assert route_after_model(state) == "tool_calls"


def test_standard_routing_detects_final_answer():
    state = build_initial_state("hello")
    state["messages"].append(AIMessage(content="final answer"))

    assert route_after_model(state) == "final"


def test_standard_loop_limit_uses_loop_index():
    assert route_loop_limit({**build_initial_state("hello", max_loops=2), "loop_index": 2}) == "continue"
    assert route_loop_limit({**build_initial_state("hello", max_loops=2), "loop_index": 3}) == "max_loops"


def test_standard_permission_routing():
    assert route_after_permission({**build_initial_state("hello"), "permission": {"status": "allowed"}}) == "allowed"
    assert (
        route_after_permission({**build_initial_state("hello"), "permission": {"status": "approval_required"}})
        == "approval_required"
    )
    assert route_after_permission({**build_initial_state("hello"), "permission": {"status": "denied"}}) == "denied"


def test_standard_approval_routing():
    assert route_after_approval({**build_initial_state("hello"), "approval": {"approved": True}}) == "approved"
    assert route_after_approval({**build_initial_state("hello"), "approval": {"approved": False}}) == "rejected"
    assert route_after_approval(build_initial_state("hello")) == "rejected"


def test_standard_graph_appends_ai_message_with_add_messages():
    model = FakeStandardModel(AIMessage(content="final answer"))
    graph = build_standard_graph(StandardGraphComponents(model=model, tools=[]))

    output = graph.invoke(build_initial_state("hello", system_prompt="system prompt"))

    assert output["final_answer"] == "final answer"
    assert len(output["messages"]) == 3
    assert isinstance(output["messages"][-1], AIMessage)
    assert model.calls[0][0][0].content == "system prompt"
    assert model.calls[0][0][1].content == "hello"


def test_standard_runtime_returns_run_result_for_final_answer():
    model = FakeStandardModel(AIMessage(content="final answer"))
    runtime = StandardLangGraphAgentRuntime(model=model, system_prompt="system prompt", max_loops=3)

    result = runtime.start("hello", thread_id="thread-test")

    assert result.thread_id == "thread-test"
    assert result.status == "completed"
    assert result.final_answer == "final answer"
    assert result.to_output() == "final answer"
    assert len(result.state["messages"]) == 3
    assert model.calls[0][0][0].content == "system prompt"
    assert model.calls[0][0][1].content == "hello"


def test_standard_runtime_run_returns_final_answer():
    runtime = StandardLangGraphAgentRuntime(model=FakeStandardModel(AIMessage(content="final answer")))

    assert runtime.run("hello") == "final answer"


def test_standard_graph_executes_safe_tool_with_toolnode_then_calls_model_again():
    model = FakeStandardModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "echo",
                        "args": {"value": "hello"},
                        "id": "call-echo",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="tool completed"),
        ]
    )
    tool = tool_spec_to_structured_tool(
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
    graph = build_standard_graph(StandardGraphComponents(model=model, tools=[tool]))

    output = graph.invoke(build_initial_state("echo hello"))

    assert output["final_answer"] == "tool completed"
    assert len(model.calls) == 2
    assert any(isinstance(message, ToolMessage) for message in output["messages"])
    tool_message = next(message for message in output["messages"] if isinstance(message, ToolMessage))
    assert tool_message.name == "echo"
    assert tool_message.tool_call_id == "call-echo"
    assert tool_message.status == "success"
    assert tool_message.content == '{"value": "hello"}'
    assert isinstance(model.calls[1][0][-1], ToolMessage)


def test_standard_runtime_executes_safe_tool_with_toolnode():
    model = FakeStandardModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "echo",
                        "args": {"value": "hello"},
                        "id": "call-echo",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="tool completed"),
        ]
    )
    tool = tool_spec_to_structured_tool(
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
    runtime = StandardLangGraphAgentRuntime(model=model, tools=[tool])

    result = runtime.start("echo hello", thread_id="thread-safe-tool")

    assert result.thread_id == "thread-safe-tool"
    assert result.status == "completed"
    assert result.final_answer == "tool completed"
    assert any(isinstance(message, ToolMessage) for message in result.state["messages"])


def test_standard_runtime_interrupts_dangerous_tool_before_toolnode():
    executed = {"value": False}
    registry = ToolRegistry()
    spec = ToolSpec(
        name="dangerous",
        description="Dangerous tool.",
        parameters={"type": "object", "properties": {}},
        dangerous=True,
        func=lambda: executed.__setitem__("value", True) or {"executed": True},
    )
    registry.register(spec)
    tool = tool_spec_to_structured_tool(spec)
    model = FakeStandardModel(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "dangerous",
                    "args": {},
                    "id": "call-dangerous",
                    "type": "tool_call",
                }
            ],
        )
    )
    runtime = StandardLangGraphAgentRuntime(
        model=model,
        tools=[tool],
        permission_gate=PermissionGate(registry),
    )

    result = runtime.start("run dangerous", thread_id="thread-dangerous")

    assert result.status == "interrupted"
    assert result.final_answer is None
    assert result.interrupt["kind"] == "approval_required"
    assert result.interrupt["permission"]["reason"] == "tool 'dangerous' is marked dangerous"
    assert result.interrupt_message.startswith("Approval required for tool call")
    assert executed["value"] is False


def test_standard_runtime_resumes_approved_dangerous_tool():
    executed = {"value": False}
    registry = ToolRegistry()
    spec = ToolSpec(
        name="dangerous",
        description="Dangerous tool.",
        parameters={"type": "object", "properties": {}},
        dangerous=True,
        func=lambda: executed.__setitem__("value", True) or {"executed": True},
    )
    registry.register(spec)
    tool = tool_spec_to_structured_tool(spec)
    model = FakeStandardModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "dangerous",
                        "args": {},
                        "id": "call-dangerous",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="dangerous completed"),
        ]
    )
    runtime = StandardLangGraphAgentRuntime(
        model=model,
        tools=[tool],
        permission_gate=PermissionGate(registry),
    )

    interrupted = runtime.start("run dangerous", thread_id="thread-dangerous-approved")
    result = runtime.resume(interrupted.thread_id, approved=True, reason="approved for test")

    assert result.status == "completed"
    assert result.final_answer == "dangerous completed"
    assert executed["value"] is True
    assert any(isinstance(message, ToolMessage) for message in result.state["messages"])
    assert result.state["approval"] == {"approved": True, "reason": "approved for test"}


def test_standard_runtime_resumes_rejected_dangerous_tool_without_execution():
    executed = {"value": False}
    registry = ToolRegistry()
    spec = ToolSpec(
        name="dangerous",
        description="Dangerous tool.",
        parameters={"type": "object", "properties": {}},
        dangerous=True,
        func=lambda: executed.__setitem__("value", True) or {"executed": True},
    )
    registry.register(spec)
    tool = tool_spec_to_structured_tool(spec)
    model = FakeStandardModel(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "dangerous",
                    "args": {},
                    "id": "call-dangerous",
                    "type": "tool_call",
                }
            ],
        )
    )
    runtime = StandardLangGraphAgentRuntime(
        model=model,
        tools=[tool],
        permission_gate=PermissionGate(registry),
    )

    interrupted = runtime.start("run dangerous", thread_id="thread-dangerous-rejected")
    result = runtime.resume(interrupted.thread_id, approved=False, reason="not allowed")

    assert result.status == "completed"
    assert result.final_answer == "Tool call rejected by approval: not allowed"
    assert executed["value"] is False
    assert not any(isinstance(message, ToolMessage) for message in result.state["messages"])
    assert result.state["approval"] == {"approved": False, "reason": "not allowed"}


def test_standard_runtime_progress_uses_standard_messages(capsys):
    model = FakeStandardModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "echo",
                        "args": {"value": "hello"},
                        "id": "call-echo",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="tool completed"),
        ]
    )
    tool = tool_spec_to_structured_tool(
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
    runtime = StandardLangGraphAgentRuntime(
        model=model,
        tools=[tool],
        progress=ProgressReporter(enabled=True),
    )

    result = runtime.start("echo hello", thread_id="thread-progress")

    assert result.final_answer == "tool completed"
    output = capsys.readouterr().err
    assert "loop 1" in output
    assert "context" in output
    assert "tool_call" in output
    assert "echo" in output
    assert "result" in output
    assert "observation" in output
    assert "loop 2" in output
    assert "done" in output


def test_standard_runtime_trace_uses_standard_messages(tmp_path):
    model = FakeStandardModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "echo",
                        "args": {"value": "hello"},
                        "id": "call-echo",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="tool completed"),
        ]
    )
    tool = tool_spec_to_structured_tool(
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
    trace_path = tmp_path / "trace.jsonl"
    runtime = StandardLangGraphAgentRuntime(
        model=model,
        tools=[tool],
        trace=TraceLogger(trace_path),
    )

    result = runtime.start("echo hello", thread_id="thread-trace")

    assert result.final_answer == "tool completed"
    trace = trace_path.read_text(encoding="utf-8")
    assert '"type": "standard_run_started"' in trace
    assert '"type": "standard_context_built"' in trace
    assert '"type": "standard_model_response"' in trace
    assert '"type": "standard_tool_execute_start"' in trace
    assert '"type": "standard_tool_message"' in trace
    assert '"type": "standard_run_finished"' in trace


def test_standard_ollama_adapter_converts_project_tool_call_to_ai_message():
    project_client = FakeProjectModelClient(
        OllamaModelClient()._parse_content(
            '{"action":"tool_call","name":"echo","arguments":{"value":"hello"}}'
        )
    )
    adapter = StandardOllamaModelClient(
        client=project_client,
        tool_schemas=[{"name": "echo", "parameters": {}}],
    )

    response = adapter.invoke([SystemMessage(content="system"), HumanMessage(content="hello")], tools=[])

    assert isinstance(response, AIMessage)
    assert response.tool_calls[0]["name"] == "echo"
    assert response.tool_calls[0]["args"] == {"value": "hello"}
    assert project_client.calls[0][1] == [{"name": "echo", "parameters": {}}]
