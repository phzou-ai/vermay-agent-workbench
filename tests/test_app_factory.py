from __future__ import annotations

from mini_agent.app_factory import RuntimeFactoryConfig, build_runtime
from mini_agent.langgraph_runtime import LangGraphAgentRuntime, ModelProviderConfig, OllamaModelAdapter


def test_app_factory_builds_runtime_with_registered_tools(tmp_path):
    runtime = build_runtime(
        RuntimeFactoryConfig(
            model=ModelProviderConfig(provider="ollama", options={"model": "test-model"}),
            trace_path=tmp_path / "trace.jsonl",
            checkpoint_path=tmp_path / "checkpoints" / "langgraph.sqlite",
            show_progress=False,
        )
    )

    tool_names = {tool.name for tool in runtime.tools}

    assert isinstance(runtime, LangGraphAgentRuntime)
    assert isinstance(runtime.model, OllamaModelAdapter)
    assert runtime.model.client.model == "test-model"
    assert runtime.permission_gate is not None
    assert runtime.trace is not None
    assert runtime.trace.path == tmp_path / "trace.jsonl"
    assert runtime.progress is not None
    assert runtime.progress.enabled is False
    assert runtime.checkpointer is not None
    assert "ssh_kubectl_get" in tool_names
    assert "weather_forecast" in tool_names
    assert len(runtime.close_callbacks) == 1
    runtime.close()
    assert runtime.close_callbacks == []
