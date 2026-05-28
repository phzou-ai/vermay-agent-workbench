from __future__ import annotations

from pathlib import Path

from mini_agent.context_builder import ContextBuilder
from mini_agent.memory import MemoryStore
from mini_agent.observation import ObservationHandler
from mini_agent.permission import PermissionGate
from mini_agent.tool_executor import ToolExecutor
from mini_agent.tool_registry import ToolRegistry
from mini_agent.tools.devops import register_devops_tools
from mini_agent.tools.devops import remote_kubernetes
from mini_agent.tools.weather import register_weather_tools
from mini_agent.tools.weather import forecast as weather_module
from mini_agent.trace import TraceLogger
from mini_agent.types import Message, ModelResponse, ToolCall
from mini_agent.langgraph_runtime import LangGraphAgentRuntime


class FakeModel:
    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = responses
        self.calls: list[list[Message]] = []

    def invoke(self, messages: list[Message], tools: list[dict]) -> ModelResponse:
        self.calls.append(messages)
        return self.responses.pop(0)


def build_full_tool_runtime(tmp_path: Path, model: FakeModel, max_steps: int = 5) -> LangGraphAgentRuntime:
    registry = ToolRegistry()
    register_devops_tools(registry)
    register_weather_tools(registry)
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


def test_langgraph_runtime_executes_mock_devops_tool(tmp_path: Path):
    model = FakeModel(
        [
            ModelResponse(
                content="Calling tool grep_logs.",
                tool_call=ToolCall(name="grep_logs", arguments={"pattern": "error"}),
            ),
            ModelResponse(content="final"),
        ]
    )

    answer = build_full_tool_runtime(tmp_path, model).run("grep nginx errors")

    assert answer == "final"
    assert len(model.calls) == 2
    assert "upstream api timeout" in model.calls[1][-1].content
    assert "upstream api responded 502" in model.calls[1][-1].content


def test_langgraph_runtime_executes_ssh_kubernetes_tool_without_live_ssh(tmp_path: Path, monkeypatch):
    class FakeSshClient:
        def run(self, command: str) -> dict:
            return {
                "ok": True,
                "command": command,
                "stdout": "NAMESPACE NAME TYPE AGE\ndefault kubernetes ClusterIP 1d\n",
                "stderr": "",
                "exit_code": 0,
            }

    monkeypatch.setattr(remote_kubernetes, "SshClient", FakeSshClient)
    model = FakeModel(
        [
            ModelResponse(
                content="Calling tool ssh_kubectl_get.",
                tool_call=ToolCall(name="ssh_kubectl_get", arguments={"resource": "services", "namespace": "all"}),
            ),
            ModelResponse(content="services ok"),
        ]
    )

    answer = build_full_tool_runtime(tmp_path, model).run("check real cluster services")

    assert answer == "services ok"
    assert len(model.calls) == 2
    assert "kubectl get services -A -o wide" in model.calls[1][-1].content
    assert "default kubernetes ClusterIP 1d" in model.calls[1][-1].content


def test_langgraph_runtime_executes_weather_tool_without_live_network(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        weather_module,
        "weather_forecast",
        lambda location, days=3: {
            "location": location,
            "days": days,
            "current": {"temp_c": "21", "condition": "Sunny"},
            "forecast": [{"date": "2026-05-26", "avg_temp_c": "22"}],
        },
    )

    registry = ToolRegistry()
    register_devops_tools(registry)
    registry.register(
        next(
            spec
            for spec in _weather_specs_with_patched_function().values()
            if spec.name == "weather_forecast"
        )
    )
    model = FakeModel(
        [
            ModelResponse(
                content="Calling tool weather_forecast.",
                tool_call=ToolCall(name="weather_forecast", arguments={"location": "Shanghai", "days": 1}),
            ),
            ModelResponse(content="weather ok"),
        ]
    )
    runtime = LangGraphAgentRuntime(
        model=model,
        registry=registry,
        context_builder=ContextBuilder(),
        permission_gate=PermissionGate(registry),
        tool_executor=ToolExecutor(registry),
        observation_handler=ObservationHandler(),
        memory=MemoryStore(tmp_path / "memory.txt"),
        trace=TraceLogger(tmp_path / "trace.jsonl"),
    )

    answer = runtime.run("weather forecast for Shanghai")

    assert answer == "weather ok"
    assert len(model.calls) == 2
    assert '"location": "Shanghai"' in model.calls[1][-1].content
    assert '"condition": "Sunny"' in model.calls[1][-1].content


def test_langgraph_runtime_blocks_registered_dangerous_tools(tmp_path: Path):
    model = FakeModel(
        [
            ModelResponse(
                content="Calling tool kubectl_apply.",
                tool_call=ToolCall(name="kubectl_apply", arguments={"manifest": "apiVersion: v1"}),
            ),
        ]
    )

    answer = build_full_tool_runtime(tmp_path, model).run("apply manifest")

    assert answer.startswith("Approval required for tool 'kubectl_apply': tool 'kubectl_apply' is marked dangerous")
    assert "thread_id:" in answer
    assert "--resume-approval true" in answer
    assert len(model.calls) == 1


def _weather_specs_with_patched_function():
    registry = ToolRegistry()
    register_weather_tools(registry)
    spec = registry.get("weather_forecast")
    spec.func = weather_module.weather_forecast
    return {"weather_forecast": spec}
