from __future__ import annotations

from mini_agent.api.service import AgentService, AgentStartOptions
from mini_agent.api.session_store import SessionStore
from mini_agent.app_factory import RuntimeFactoryConfig
from mini_agent.langgraph_runtime.results import RunResult
from mini_agent.mcp_selection import MCPPromptSelectionConfig, MCPResourceSelectionConfig, MCPSelectionConfig
from mini_agent.storage import AgentStore


class FakeRuntime:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.closed = False

    def start(self, user_input, thread_id=None):
        return self.responses.pop(0)

    def resume(self, thread_id, approved, reason=None):
        return self.responses.pop(0)

    def close(self):
        self.closed = True


def test_service_resumes_default_session_with_default_runtime(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite")
    runtime = FakeRuntime(
        [
            RunResult(thread_id="session-1", interrupt={"kind": "approval_required"}),
            RunResult(thread_id="session-1", final_answer="approved"),
        ]
    )
    built_configs = []

    def build(config):
        built_configs.append(config)
        return runtime

    service = AgentService(
        session_store=SessionStore(store),
        default_config=RuntimeFactoryConfig(show_progress=False),
        runtime_builder=build,
    )

    service.start("dangerous", thread_id="session-1")
    record = service.get_session("session-1")
    assert record is not None
    assert record.max_loops is None

    result = service.resume("session-1", approved=True)

    assert result.final_answer == "approved"
    assert len(built_configs) == 1
    service.close()
    store.close()


def test_service_persists_explicit_max_loops_override(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite")
    runtime = FakeRuntime([RunResult(thread_id="session-1", final_answer="done")])
    service = AgentService(
        session_store=SessionStore(store),
        default_config=RuntimeFactoryConfig(show_progress=False),
        runtime_builder=lambda config: runtime,
    )

    service.start("hello", thread_id="session-1", options=AgentStartOptions(max_loops=2))

    record = service.get_session("session-1")
    assert record is not None
    assert record.max_loops == 2
    service.close()
    store.close()


def test_service_preserves_mcp_selection_on_resume(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite")
    runtime = FakeRuntime(
        [
            RunResult(thread_id="session-1", interrupt={"kind": "approval_required"}),
            RunResult(thread_id="session-1", final_answer="approved"),
        ]
    )
    built_configs = []

    def build(config):
        built_configs.append(config)
        return runtime

    service = AgentService(
        session_store=SessionStore(store),
        default_config=RuntimeFactoryConfig(show_progress=False),
        runtime_builder=build,
    )
    selection = MCPSelectionConfig(
        servers=("k8s",),
        prompts=(MCPPromptSelectionConfig(server="k8s", name="k8s-debug", arguments={"service": "phzou-core"}),),
        resources=(MCPResourceSelectionConfig(server="k8s", uri="k8s://cluster/default/services"),),
    )

    service.start("dangerous", thread_id="session-1", options=AgentStartOptions(mcp=selection))
    service.resume("session-1", approved=True)

    assert built_configs[1].mcp_servers == ("k8s",)
    assert built_configs[1].mcp_prompts == ("k8s:k8s-debug?service=phzou-core",)
    assert built_configs[1].mcp_resources == ("k8s:k8s://cluster/default/services",)
    assert built_configs[2].mcp_servers == ("k8s",)
    assert built_configs[2].mcp_prompts == ("k8s:k8s-debug?service=phzou-core",)
    assert built_configs[2].mcp_resources == ("k8s:k8s://cluster/default/services",)
    service.close()
    store.close()
