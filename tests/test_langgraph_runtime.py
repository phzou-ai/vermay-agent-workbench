from __future__ import annotations

from pathlib import Path

from mini_agent.context_builder import ContextBuilder
from mini_agent.memory import MemoryStore
from mini_agent.observation import ObservationHandler
from mini_agent.permission import PermissionGate
from mini_agent.tool_executor import ToolExecutor
from mini_agent.tool_registry import ToolRegistry
from mini_agent.trace import TraceLogger
from mini_agent.types import Message, ModelResponse, ToolCall, ToolSpec
from mini_agent_langgraph import LangGraphAgentRuntime
from mini_agent_langgraph.routing import route_after_model, route_after_permission, route_after_step


class FakeModel:
    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = responses
        self.calls: list[list[Message]] = []

    def invoke(self, messages: list[Message], tools: list[dict]) -> ModelResponse:
        self.calls.append(messages)
        return self.responses.pop(0)


def build_test_runtime(tmp_path: Path, model: FakeModel, max_steps: int = 5) -> LangGraphAgentRuntime:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="echo",
            description="Echo test value.",
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
            description="Dangerous test tool.",
            parameters={"type": "object", "properties": {}},
            dangerous=True,
            func=lambda: {"executed": True},
        )
    )

    return LangGraphAgentRuntime(
        model=model,
        registry=registry,
        context_builder=ContextBuilder(),
        permission_gate=PermissionGate(registry),
        tool_executor=ToolExecutor(registry),
        observation_handler=ObservationHandler(),
        memory=MemoryStore(tmp_path / "memory.txt"),
        trace=TraceLogger(tmp_path / "trace.jsonl"),
        max_steps=max_steps,
    )


def test_langgraph_runtime_runs_safe_tool_then_final_answer(tmp_path: Path):
    model = FakeModel(
        [
            ModelResponse(content="Calling tool echo.", tool_call=ToolCall(name="echo", arguments={"value": "hello"})),
            ModelResponse(content="final answer"),
        ]
    )
    runtime = build_test_runtime(tmp_path, model)

    answer = runtime.run("say hello")

    assert answer == "final answer"
    assert len(model.calls) == 2
    assert [message.role for message in model.calls[1]] == ["system", "user", "tool"]
    assert model.calls[1][-1].name == "echo"
    assert '"value": "hello"' in model.calls[1][-1].content


def test_langgraph_runtime_stops_for_dangerous_tool_approval(tmp_path: Path):
    model = FakeModel(
        [
            ModelResponse(content="Calling tool dangerous.", tool_call=ToolCall(name="dangerous")),
        ]
    )
    runtime = build_test_runtime(tmp_path, model)

    answer = runtime.run("run dangerous action")

    assert answer == "Approval required for tool 'dangerous': tool 'dangerous' is marked dangerous"
    assert len(model.calls) == 1


def test_langgraph_runtime_enforces_max_steps(tmp_path: Path):
    model = FakeModel(
        [
            ModelResponse(content="Calling tool echo.", tool_call=ToolCall(name="echo", arguments={"value": "one"})),
            ModelResponse(content="Calling tool echo.", tool_call=ToolCall(name="echo", arguments={"value": "two"})),
        ]
    )
    runtime = build_test_runtime(tmp_path, model, max_steps=2)

    answer = runtime.run("loop")

    assert answer == "Stopped after max_steps=2"
    assert len(model.calls) == 2


def test_langgraph_routing_after_model():
    assert route_after_model({"final_answer": "done", "tool_call": None}) == "final"
    assert route_after_model({"final_answer": None, "tool_call": ToolCall(name="echo")}) == "tool_call"


def test_langgraph_routing_after_permission():
    class Decision:
        def __init__(self, allowed: bool, requires_approval: bool) -> None:
            self.allowed = allowed
            self.requires_approval = requires_approval

    assert route_after_permission({"permission_decision": Decision(True, False)}) == "allowed"
    assert route_after_permission({"permission_decision": Decision(False, True)}) == "approval_required"
    assert route_after_permission({"permission_decision": Decision(False, False)}) == "denied"
    assert route_after_permission({"permission_decision": None}) == "denied"


def test_langgraph_routing_after_step():
    assert route_after_step({"step": 1, "max_steps": 2}) == "continue"
    assert route_after_step({"step": 3, "max_steps": 2}) == "max_steps"
