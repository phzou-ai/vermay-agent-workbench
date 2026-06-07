from __future__ import annotations

from dataclasses import dataclass, field

from vermay_agent.main_agent import (
    LocalMessageResult,
    LocalTaskResult,
    LocalTaskRunResult,
    MainAgentCore,
    MainAgentRequest,
    MainAgentStore,
    MessageRecord,
    MessageRole,
    RemoteAgentResult,
    RemoteAgentSendResult,
    RouteDecisionKind,
    TaskStatus,
)
from vermay_agent.storage import AgentStore


@dataclass
class FakeResponder:
    calls: list[list[MessageRecord]] = field(default_factory=list)

    def respond(self, messages: list[MessageRecord]) -> list[dict]:
        self.calls.append(messages)
        return [{"kind": "text", "text": "model answer"}]


@dataclass
class FakeTaskRunner:
    calls: list[tuple[list[MessageRecord], str]] = field(default_factory=list)

    def run(self, messages: list[MessageRecord], *, thread_id: str) -> LocalTaskRunResult:
        self.calls.append((messages, thread_id))
        return LocalTaskRunResult(
            status=TaskStatus.COMPLETED,
            parts=[{"kind": "text", "text": "task answer"}],
        )


@dataclass
class FakeRemoteAgentClient:
    responses: list[RemoteAgentSendResult]
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    def send_message(self, *, agent, request, context_id: str, message_id: str) -> RemoteAgentSendResult:
        self.calls.append((agent.agent_id, context_id, message_id))
        return self.responses.pop(0)


def test_main_agent_core_local_message_persists_messages_without_task(tmp_path):
    store = MainAgentStore(AgentStore(tmp_path / "agent.sqlite"))
    responder = FakeResponder()
    core = MainAgentCore(store=store, local_message_responder=responder)

    result = core.handle_message(
        MainAgentRequest(
            context_id=None,
            message_id="msg-user-1",
            role=MessageRole.USER,
            parts=[{"kind": "text", "text": "hello"}],
            metadata={"executionMode": "message"},
        )
    )

    assert isinstance(result, LocalMessageResult)
    assert result.kind == RouteDecisionKind.LOCAL_MESSAGE
    assert result.input_message_id == "msg-user-1"
    assert result.parts == [{"kind": "text", "text": "model answer"}]
    messages = store.list_context_messages(result.context_id)
    assert [message.role for message in messages] == [MessageRole.USER, MessageRole.AGENT]
    assert [message.message_id for message in messages] == ["msg-user-1", result.message_id]
    assert store.list_context_tasks(result.context_id) == []
    assert len(responder.calls) == 1
    assert [message.message_id for message in responder.calls[0]] == ["msg-user-1"]


def test_main_agent_core_local_message_receives_same_context_history(tmp_path):
    store = MainAgentStore(AgentStore(tmp_path / "agent.sqlite"))
    responder = FakeResponder()
    core = MainAgentCore(store=store, local_message_responder=responder)

    first = core.handle_message(
        MainAgentRequest(
            context_id=None,
            message_id="msg-user-1",
            role=MessageRole.USER,
            parts=[{"kind": "text", "text": "my name is Ada"}],
            metadata={"executionMode": "message"},
        )
    )
    second = core.handle_message(
        MainAgentRequest(
            context_id=first.context_id,
            message_id="msg-user-2",
            role=MessageRole.USER,
            parts=[{"kind": "text", "text": "what is my name?"}],
            metadata={"executionMode": "message"},
        )
    )

    assert isinstance(second, LocalMessageResult)
    assert len(responder.calls) == 2
    assert [message.message_id for message in responder.calls[1]] == [
        "msg-user-1",
        first.message_id,
        "msg-user-2",
    ]
    assert [message.role for message in responder.calls[1]] == [
        MessageRole.USER,
        MessageRole.AGENT,
        MessageRole.USER,
    ]


def test_main_agent_core_local_task_creates_task_without_responder_call(tmp_path):
    store = MainAgentStore(AgentStore(tmp_path / "agent.sqlite"))
    responder = FakeResponder()
    core = MainAgentCore(store=store, local_message_responder=responder)
    context = store.create_context(context_id="ctx-1")

    result = core.handle_message(
        MainAgentRequest(
            context_id=context.context_id,
            message_id="msg-user-1",
            role=MessageRole.USER,
            parts=[{"kind": "text", "text": "run"}],
            metadata={"executionMode": "task"},
        )
    )

    assert isinstance(result, LocalTaskResult)
    assert result.kind == RouteDecisionKind.LOCAL_TASK
    assert result.context_id == "ctx-1"
    assert store.get_task(result.task_id) is not None
    assert responder.calls == []


def test_main_agent_core_local_task_runner_receives_same_context_history(tmp_path):
    store = MainAgentStore(AgentStore(tmp_path / "agent.sqlite"))
    runner = FakeTaskRunner()
    core = MainAgentCore(
        store=store,
        local_message_responder=FakeResponder(),
        local_task_runner=runner,
    )
    context = store.create_context(context_id="ctx-1")
    store.append_message(
        message_id="msg-user-1",
        context_id=context.context_id,
        role=MessageRole.USER,
        parts=[{"kind": "text", "text": "remember project alpha"}],
    )
    store.append_message(
        message_id="msg-agent-1",
        context_id=context.context_id,
        role=MessageRole.AGENT,
        parts=[{"kind": "text", "text": "project alpha noted"}],
    )

    result = core.handle_message(
        MainAgentRequest(
            context_id=context.context_id,
            message_id="msg-user-2",
            role=MessageRole.USER,
            parts=[{"kind": "text", "text": "run a task for that project"}],
            metadata={"executionMode": "task"},
        )
    )

    assert isinstance(result, LocalTaskResult)
    assert len(runner.calls) == 1
    assert [message.message_id for message in runner.calls[0][0]] == [
        "msg-user-1",
        "msg-agent-1",
        "msg-user-2",
    ]
    assert [message.role for message in runner.calls[0][0]] == [
        MessageRole.USER,
        MessageRole.AGENT,
        MessageRole.USER,
    ]


def test_main_agent_core_context_window_is_bounded_to_recent_ten_messages(tmp_path):
    store = MainAgentStore(AgentStore(tmp_path / "agent.sqlite"))
    responder = FakeResponder()
    core = MainAgentCore(store=store, local_message_responder=responder)
    context = store.create_context(context_id="ctx-1")
    for index in range(12):
        store.append_message(
            message_id=f"msg-history-{index}",
            context_id=context.context_id,
            role=MessageRole.USER if index % 2 == 0 else MessageRole.AGENT,
            parts=[{"kind": "text", "text": f"history {index}"}],
        )

    core.handle_message(
        MainAgentRequest(
            context_id=context.context_id,
            message_id="msg-user-current",
            role=MessageRole.USER,
            parts=[{"kind": "text", "text": "current"}],
            metadata={"executionMode": "message"},
        )
    )

    assert [message.message_id for message in responder.calls[0]] == [
        "msg-history-3",
        "msg-history-4",
        "msg-history-5",
        "msg-history-6",
        "msg-history-7",
        "msg-history-8",
        "msg-history-9",
        "msg-history-10",
        "msg-history-11",
        "msg-user-current",
    ]


def test_main_agent_core_local_task_runner_persists_output_message_artifact_and_events(tmp_path):
    store = MainAgentStore(AgentStore(tmp_path / "agent.sqlite"))
    runner = FakeTaskRunner()
    core = MainAgentCore(
        store=store,
        local_message_responder=FakeResponder(),
        local_task_runner=runner,
    )
    context = store.create_context(context_id="ctx-1")

    result = core.handle_message(
        MainAgentRequest(
            context_id=context.context_id,
            message_id="msg-user-1",
            role=MessageRole.USER,
            parts=[{"kind": "text", "text": "run"}],
            metadata={"executionMode": "task"},
        )
    )

    assert isinstance(result, LocalTaskResult)
    task = store.get_task(result.task_id)
    assert task is not None
    assert task.status == TaskStatus.COMPLETED
    assert task.output_message_id is not None
    assert [message.role for message in store.list_context_messages("ctx-1")] == [
        MessageRole.USER,
        MessageRole.AGENT,
    ]
    assert store.get_message(task.output_message_id).parts == [{"kind": "text", "text": "task answer"}]
    artifacts = store.list_task_artifacts(result.task_id)
    assert len(artifacts) == 1
    assert artifacts[0].parts == [{"kind": "text", "text": "task answer"}]
    assert artifacts[0].metadata["kind"] == "final_answer"
    assert [event.type for event in store.list_task_events(result.task_id)] == [
        "task_created",
        "task_started",
        "task_artifact_created",
        "task_completed",
    ]
    assert len(runner.calls) == 1
    assert [message.message_id for message in runner.calls[0][0]] == ["msg-user-1"]
    assert runner.calls[0][1] == task.runtime_thread_id


def test_main_agent_core_local_task_runner_failure_marks_task_failed(tmp_path):
    class FailingRunner:
        def run(self, messages: list[MessageRecord], *, thread_id: str) -> LocalTaskRunResult:
            raise RuntimeError("runtime failed")

    store = MainAgentStore(AgentStore(tmp_path / "agent.sqlite"))
    core = MainAgentCore(
        store=store,
        local_message_responder=FakeResponder(),
        local_task_runner=FailingRunner(),
    )
    context = store.create_context(context_id="ctx-1")

    result = core.handle_message(
        MainAgentRequest(
            context_id=context.context_id,
            message_id="msg-user-1",
            role=MessageRole.USER,
            parts=[{"kind": "text", "text": "run"}],
            metadata={"executionMode": "task"},
        )
    )

    task = store.get_task(result.task_id)
    assert task is not None
    assert task.status == TaskStatus.FAILED
    assert task.error_code == "RuntimeError"
    assert task.error_message == "runtime failed"
    assert [event.type for event in store.list_task_events(result.task_id)] == [
        "task_created",
        "task_started",
        "task_failed",
    ]


def test_main_agent_core_local_task_runner_can_leave_task_running(tmp_path):
    class RunningRunner:
        def run(self, messages: list[MessageRecord], *, thread_id: str) -> LocalTaskRunResult:
            return LocalTaskRunResult(status=TaskStatus.RUNNING)

    store = MainAgentStore(AgentStore(tmp_path / "agent.sqlite"))
    core = MainAgentCore(
        store=store,
        local_message_responder=FakeResponder(),
        local_task_runner=RunningRunner(),
    )
    context = store.create_context(context_id="ctx-1")

    result = core.handle_message(
        MainAgentRequest(
            context_id=context.context_id,
            message_id="msg-user-1",
            role=MessageRole.USER,
            parts=[{"kind": "text", "text": "run and hold"}],
            metadata={"executionMode": "task"},
        )
    )

    task = store.get_task(result.task_id)
    assert task is not None
    assert task.status == TaskStatus.RUNNING
    assert task.output_message_id is None
    assert [event.type for event in store.list_task_events(result.task_id)] == [
        "task_created",
        "task_started",
    ]


def test_main_agent_core_unknown_context_is_rejected(tmp_path):
    store = MainAgentStore(AgentStore(tmp_path / "agent.sqlite"))
    core = MainAgentCore(store=store, local_message_responder=FakeResponder())

    try:
        core.handle_message(
            MainAgentRequest(
                context_id="ctx-missing",
                message_id="msg-user-1",
                role=MessageRole.USER,
                parts=[{"kind": "text", "text": "hello"}],
                metadata={"executionMode": "message"},
            )
        )
    except ValueError as exc:
        assert str(exc) == "unknown context: ctx-missing"
    else:
        raise AssertionError("expected unknown context to fail")


def test_main_agent_core_remote_message_records_delegation_and_assistant_message(tmp_path):
    store = MainAgentStore(AgentStore(tmp_path / "agent.sqlite"))
    store.upsert_registered_agent(
        agent_id="agent-child-1",
        name="Child agent",
        card_url="http://127.0.0.1:9001/.well-known/agent-card.json",
    )
    remote_client = FakeRemoteAgentClient(
        responses=[
            RemoteAgentSendResult(
                kind="message",
                context_id="remote-ctx-1",
                message_id="remote-msg-1",
                parts=[{"kind": "text", "text": "remote answer"}],
            )
        ]
    )
    core = MainAgentCore(
        store=store,
        local_message_responder=FakeResponder(),
        remote_agent_client=remote_client,
    )

    result = core.handle_message(
        MainAgentRequest(
            context_id=None,
            message_id="msg-user-1",
            role=MessageRole.USER,
            parts=[{"kind": "text", "text": "delegate"}],
            metadata={"route": "remote_agent", "targetAgentId": "agent-child-1"},
        )
    )

    assert isinstance(result, RemoteAgentResult)
    assert result.target_agent_id == "agent-child-1"
    assert result.message_id is not None
    assert result.parts == [{"kind": "text", "text": "remote answer"}]
    assert remote_client.calls == [("agent-child-1", result.context_id, "msg-user-1")]
    messages = store.list_context_messages(result.context_id)
    assert [message.message_id for message in messages] == ["msg-user-1", result.message_id]
    assert messages[-1].metadata["remoteMessageId"] == "remote-msg-1"
    delegation = store.get_delegated_task(result.delegation_id)
    assert delegation is not None
    assert delegation.result_kind == "message"
    assert delegation.remote_agent_id == "agent-child-1"
    assert delegation.remote_context_id == "remote-ctx-1"
    assert delegation.remote_message_id == "remote-msg-1"


def test_main_agent_core_remote_task_records_proxy_task_and_delegation(tmp_path):
    store = MainAgentStore(AgentStore(tmp_path / "agent.sqlite"))
    store.upsert_registered_agent(
        agent_id="agent-child-1",
        name="Child agent",
        card_url="http://127.0.0.1:9001/.well-known/agent-card.json",
    )
    remote_client = FakeRemoteAgentClient(
        responses=[
            RemoteAgentSendResult(
                kind="task",
                context_id="remote-ctx-1",
                task_id="remote-task-1",
                status="working",
            )
        ]
    )
    core = MainAgentCore(
        store=store,
        local_message_responder=FakeResponder(),
        remote_agent_client=remote_client,
    )

    result = core.handle_message(
        MainAgentRequest(
            context_id=None,
            message_id="msg-user-1",
            role=MessageRole.USER,
            parts=[{"kind": "text", "text": "delegate"}],
            metadata={"route": "remote_agent", "targetAgentId": "agent-child-1"},
        )
    )

    assert isinstance(result, RemoteAgentResult)
    assert result.task_id is not None
    task = store.get_task(result.task_id)
    assert task is not None
    assert task.assigned_agent_id == "agent-child-1"
    assert task.status == TaskStatus.RUNNING
    events = store.list_task_events(task.task_id)
    assert [event.type for event in events] == ["task_delegated"]
    assert events[0].payload["remote_task_id"] == "remote-task-1"
    delegation = store.get_delegated_task(result.delegation_id)
    assert delegation is not None
    assert delegation.result_kind == "task"
    assert delegation.local_task_id == task.task_id
    assert delegation.remote_task_id == "remote-task-1"


def test_main_agent_core_auto_routes_to_registered_agent_by_keyword(tmp_path):
    store = MainAgentStore(AgentStore(tmp_path / "agent.sqlite"))
    store.upsert_registered_agent(
        agent_id="agent-k8s",
        name="Kubernetes agent",
        card_url="http://127.0.0.1:9001/.well-known/agent-card.json",
        metadata={"keywords": ["kubernetes"]},
    )
    remote_client = FakeRemoteAgentClient(
        responses=[
            RemoteAgentSendResult(
                kind="message",
                context_id="remote-ctx-1",
                message_id="remote-msg-1",
                parts=[{"kind": "text", "text": "k8s answer"}],
            )
        ]
    )
    core = MainAgentCore(
        store=store,
        local_message_responder=FakeResponder(),
        remote_agent_client=remote_client,
    )

    result = core.handle_message(
        MainAgentRequest(
            context_id=None,
            message_id="msg-user-1",
            role=MessageRole.USER,
            parts=[{"kind": "text", "text": "check kubernetes pods"}],
            metadata={"executionMode": "auto"},
        )
    )

    assert isinstance(result, RemoteAgentResult)
    assert result.target_agent_id == "agent-k8s"
    assert remote_client.calls == [("agent-k8s", result.context_id, "msg-user-1")]
    decision = store.get_route_decision(result.route_decision_id)
    assert decision.kind == RouteDecisionKind.REMOTE_AGENT
    assert decision.reason == "auto route matched registered agent keyword: kubernetes"
    assert decision.metadata == {"source": "keyword_match", "keyword": "kubernetes"}


def test_main_agent_core_auto_routes_to_registered_agent_by_skill_tag(tmp_path):
    store = MainAgentStore(AgentStore(tmp_path / "agent.sqlite"))
    store.upsert_registered_agent(
        agent_id="agent-sql",
        name="SQL agent",
        card_url="http://127.0.0.1:9001/.well-known/agent-card.json",
        card_json={"skills": [{"id": "sqlite-debug", "tags": ["sqlite", "database"]}]},
    )
    remote_client = FakeRemoteAgentClient(
        responses=[
            RemoteAgentSendResult(
                kind="message",
                context_id="remote-ctx-1",
                message_id="remote-msg-1",
                parts=[{"kind": "text", "text": "sql answer"}],
            )
        ]
    )
    core = MainAgentCore(
        store=store,
        local_message_responder=FakeResponder(),
        remote_agent_client=remote_client,
    )

    result = core.handle_message(
        MainAgentRequest(
            context_id=None,
            message_id="msg-user-1",
            role=MessageRole.USER,
            parts=[{"kind": "text", "text": "debug sqlite trace events"}],
            metadata={"executionMode": "auto"},
        )
    )

    assert isinstance(result, RemoteAgentResult)
    assert result.target_agent_id == "agent-sql"
    decision = store.get_route_decision(result.route_decision_id)
    assert decision.metadata == {"source": "keyword_match", "keyword": "sqlite"}


def test_main_agent_core_remote_route_requires_registered_enabled_agent_and_client(tmp_path):
    store = MainAgentStore(AgentStore(tmp_path / "agent.sqlite"))
    core = MainAgentCore(store=store, local_message_responder=FakeResponder())

    try:
        core.handle_message(
            MainAgentRequest(
                context_id=None,
                message_id="msg-user-1",
                role=MessageRole.USER,
                parts=[{"kind": "text", "text": "delegate"}],
                metadata={"route": "remote_agent"},
            )
        )
    except ValueError as exc:
        assert str(exc) == "remote_agent route requires metadata.targetAgentId"
    else:
        raise AssertionError("expected missing target to fail")

    store.upsert_registered_agent(
        agent_id="agent-child-1",
        name="Child agent",
        card_url="http://127.0.0.1:9001/.well-known/agent-card.json",
        enabled=False,
    )
    try:
        core.handle_message(
            MainAgentRequest(
                context_id=None,
                message_id="msg-user-2",
                role=MessageRole.USER,
                parts=[{"kind": "text", "text": "delegate"}],
                metadata={"route": "remote_agent", "targetAgentId": "agent-child-1"},
            )
        )
    except ValueError as exc:
        assert str(exc) == "registered agent is disabled: agent-child-1"
    else:
        raise AssertionError("expected disabled agent to fail")
