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
from mini_agent.langgraph_runtime import LangGraphAgentRuntime
from mini_agent.langgraph_runtime.routing import route_after_approval, route_after_model, route_after_permission, route_after_step
from mini_agent.langgraph_runtime.streaming import parse_stream_modes, summarize_stream_chunk


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


def test_langgraph_runtime_start_returns_run_result_for_final_answer(tmp_path: Path):
    model = FakeModel([ModelResponse(content="final answer")])
    runtime = build_test_runtime(tmp_path, model)

    result = runtime.start("say hello")

    assert result.thread_id == runtime.thread_id
    assert result.final_answer == "final answer"
    assert result.interrupt is None
    assert result.interrupt_message is None
    assert result.stop_message is None
    assert result.to_output() == "final answer"


def test_langgraph_runtime_streams_safe_tool_then_final_answer(tmp_path: Path):
    model = FakeModel(
        [
            ModelResponse(content="Calling tool echo.", tool_call=ToolCall(name="echo", arguments={"value": "hello"})),
            ModelResponse(content="final answer"),
        ]
    )
    runtime = build_test_runtime(tmp_path, model)

    answer = runtime.run("say hello", stream_modes=("updates", "values", "custom"))

    assert answer == "final answer"
    assert len(model.calls) == 2


def test_langgraph_runtime_streams_approval_interrupt(tmp_path: Path):
    model = FakeModel(
        [
            ModelResponse(content="Calling tool dangerous.", tool_call=ToolCall(name="dangerous")),
        ]
    )
    runtime = build_test_runtime(tmp_path, model)

    answer = runtime.run("run dangerous action", stream_modes=("updates", "custom"))

    assert answer.startswith("Approval required for tool 'dangerous': tool 'dangerous' is marked dangerous")
    assert "thread_id:" in answer


def test_langgraph_runtime_start_returns_run_result_for_approval_interrupt(tmp_path: Path):
    model = FakeModel(
        [
            ModelResponse(content="Calling tool dangerous.", tool_call=ToolCall(name="dangerous")),
        ]
    )
    runtime = build_test_runtime(tmp_path, model)

    result = runtime.start("run dangerous action")

    assert result.thread_id == runtime.thread_id
    assert result.final_answer is None
    assert result.interrupt is not None
    assert isinstance(result.interrupt, dict)
    assert result.interrupt["tool_call"]["name"] == "dangerous"
    assert result.interrupt_message is not None
    assert result.interrupt_message.startswith("Approval required for tool 'dangerous'")
    assert result.to_output() == result.interrupt_message


def test_langgraph_runtime_stops_for_dangerous_tool_approval(tmp_path: Path):
    model = FakeModel(
        [
            ModelResponse(content="Calling tool dangerous.", tool_call=ToolCall(name="dangerous")),
        ]
    )
    runtime = build_test_runtime(tmp_path, model)

    answer = runtime.run("run dangerous action")

    assert answer.startswith("Approval required for tool 'dangerous': tool 'dangerous' is marked dangerous")
    assert "thread_id:" in answer
    assert "--resume-approval true" in answer
    assert len(model.calls) == 1


def test_langgraph_runtime_resume_returns_run_result(tmp_path: Path):
    model = FakeModel(
        [
            ModelResponse(content="Calling tool dangerous.", tool_call=ToolCall(name="dangerous")),
            ModelResponse(content="dangerous completed"),
        ]
    )
    runtime = build_test_runtime(tmp_path, model)

    runtime.start("run dangerous action")
    result = runtime.resume(approved=True, reason="approved for test")

    assert result.thread_id == runtime.thread_id
    assert result.final_answer == "dangerous completed"
    assert result.interrupt is None
    assert result.interrupt_message is None
    assert result.to_output() == "dangerous completed"


def test_langgraph_runtime_resumes_approval_with_rejection(tmp_path: Path):
    model = FakeModel(
        [
            ModelResponse(content="Calling tool dangerous.", tool_call=ToolCall(name="dangerous")),
        ]
    )
    runtime = build_test_runtime(tmp_path, model)

    runtime.run("run dangerous action")
    answer = runtime.resume_approval(approved=False, reason="not allowed")

    assert answer == "Tool call rejected by approval: not allowed"
    assert len(model.calls) == 1


def test_langgraph_runtime_resumes_approval_with_execution(tmp_path: Path):
    model = FakeModel(
        [
            ModelResponse(content="Calling tool dangerous.", tool_call=ToolCall(name="dangerous")),
            ModelResponse(content="dangerous completed"),
        ]
    )
    runtime = build_test_runtime(tmp_path, model)

    runtime.run("run dangerous action")
    answer = runtime.resume_approval(approved=True, reason="approved for test")

    assert answer == "dangerous completed"
    assert len(model.calls) == 2
    assert '"executed": true' in model.calls[1][-1].content


def test_langgraph_runtime_interactive_approval_rejection(tmp_path: Path):
    model = FakeModel(
        [
            ModelResponse(content="Calling tool dangerous.", tool_call=ToolCall(name="dangerous")),
        ]
    )
    runtime = build_test_runtime(tmp_path, model)
    prompts: list[tuple[str, str]] = []

    def reject(message: str, thread_id: str) -> tuple[bool, str]:
        prompts.append((message, thread_id))
        return False, "not allowed interactively"

    answer = runtime.run_with_interactive_approval("run dangerous action", reject)

    assert answer == "Tool call rejected by approval: not allowed interactively"
    assert len(prompts) == 1
    assert prompts[0][0].startswith("Approval required for tool 'dangerous'")
    assert prompts[0][1] == runtime.thread_id
    assert len(model.calls) == 1


def test_langgraph_runtime_interactive_approval_execution(tmp_path: Path):
    model = FakeModel(
        [
            ModelResponse(content="Calling tool dangerous.", tool_call=ToolCall(name="dangerous")),
            ModelResponse(content="dangerous completed"),
        ]
    )
    runtime = build_test_runtime(tmp_path, model)

    answer = runtime.run_with_interactive_approval(
        "run dangerous action",
        lambda message, thread_id: (True, "approved interactively"),
    )

    assert answer == "dangerous completed"
    assert len(model.calls) == 2
    assert '"executed": true' in model.calls[1][-1].content


def test_langgraph_runtime_interactive_approval_stops_after_round_limit(tmp_path: Path):
    model = FakeModel(
        [
            ModelResponse(content="Calling tool dangerous.", tool_call=ToolCall(name="dangerous")),
            ModelResponse(content="Calling tool dangerous.", tool_call=ToolCall(name="dangerous")),
        ]
    )
    runtime = build_test_runtime(tmp_path, model)
    prompts = 0

    def approve(message: str, thread_id: str) -> tuple[bool, str]:
        nonlocal prompts
        prompts += 1
        return True, "approved interactively"

    answer = runtime.run_with_interactive_approval("run dangerous action", approve)

    assert answer == "Stopped after 1 approval rounds."
    assert prompts == 1
    assert len(model.calls) == 2


def test_langgraph_runtime_resumes_approval_from_sqlite_checkpoint(tmp_path: Path):
    checkpoint_path = tmp_path / "checkpoints.sqlite"
    first_model = FakeModel(
        [
            ModelResponse(content="Calling tool dangerous.", tool_call=ToolCall(name="dangerous")),
        ]
    )
    first_runtime = build_test_runtime(tmp_path, first_model)
    first_runtime.checkpoint_path = checkpoint_path
    first_runtime.thread_id = "approval-thread"
    first_runtime.__post_init__()

    first_runtime.run("run dangerous action")

    second_model = FakeModel([ModelResponse(content="resumed final")])
    second_runtime = build_test_runtime(tmp_path, second_model)
    second_runtime.checkpoint_path = checkpoint_path
    second_runtime.__post_init__()

    answer = second_runtime.resume_approval(approved=True, thread_id="approval-thread")

    assert answer == "resumed final"
    assert len(second_model.calls) == 1


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


def test_langgraph_routing_after_approval():
    assert route_after_approval({"approval_result": {"approved": True}}) == "approved"
    assert route_after_approval({"approval_result": {"approved": False}}) == "rejected"
    assert route_after_approval({"approval_result": None}) == "rejected"


def test_langgraph_routing_after_step():
    assert route_after_step({"step": 1, "max_steps": 2}) == "continue"
    assert route_after_step({"step": 3, "max_steps": 2}) == "max_steps"


def test_parse_stream_modes():
    assert parse_stream_modes(None) == ("updates", "custom")
    assert parse_stream_modes(["updates,values", "debug"]) == ("updates", "values", "debug")


def test_summarize_stream_chunk():
    assert summarize_stream_chunk("updates", {"call_model": {"tool_call": object()}}) == "call_model -> tool_call"
    assert "step=2" in summarize_stream_chunk("values", {"step": 2, "messages": [], "observations": []})
