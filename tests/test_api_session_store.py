from __future__ import annotations

from vermay_agent.api.session_models import TaskStatus
from vermay_agent.api.session_store import SessionStore
from vermay_agent.langgraph_runtime.results import RunResult
from vermay_agent.storage import AgentStore


def test_session_store_persists_session_task_and_events_across_reopening(tmp_path):
    path = tmp_path / "agent.sqlite"
    store = AgentStore(path)
    sessions = SessionStore(store)
    session = sessions.create_session(
        session_id="session-1",
        context_id="ctx-1",
        title="Ops Chat",
        metadata={"source": "test"},
    )
    task = sessions.create_task(
        task_id="task-1",
        session_id=session.session_id,
        thread_id="task:task-1:attempt:1",
        user_input="hello",
        model={"provider": "ollama", "options": {"model": "test"}},
        max_loops=3,
        mcp={
            "servers": ["k8s"],
            "prompts": [{"server": "k8s", "name": "k8s-debug"}],
            "resources": [{"server": "k8s", "uri": "k8s://cluster/default/services"}],
        },
    )
    sessions.append_task_event(task_id=task.task_id, event_type="task_started", status="running")
    sessions.save_task_result(
        task_id=task.task_id,
        result=RunResult(
            thread_id="task:task-1:attempt:1",
            final_answer="done",
            state={"raw": "not persisted"},
        ),
        model={"provider": "ollama", "options": {"model": "test"}},
        max_loops=3,
        mcp={
            "servers": ["k8s"],
            "prompts": [{"server": "k8s", "name": "k8s-debug"}],
            "resources": [{"server": "k8s", "uri": "k8s://cluster/default/services"}],
        },
    )
    store.close()

    reopened = AgentStore(path)
    reopened_sessions = SessionStore(reopened)
    session_record = reopened_sessions.get_session("session-1")
    task_record = reopened_sessions.get_task("task-1")
    events = reopened_sessions.list_task_events("task-1")
    artifacts = reopened_sessions.list_task_artifacts("task-1")

    assert session_record is not None
    assert session_record.session_id == "session-1"
    assert session_record.context_id == "ctx-1"
    assert session_record.metadata == {"source": "test"}
    assert task_record is not None
    assert task_record.task_id == "task-1"
    assert task_record.session_id == "session-1"
    assert task_record.thread_id == "task:task-1:attempt:1"
    assert task_record.root_task_id == "task-1"
    assert task_record.retry_of_task_id is None
    assert task_record.status == TaskStatus.COMPLETED
    assert task_record.to_dict()["status"] == "completed"
    assert task_record.final_answer == "done"
    assert task_record.model == {"provider": "ollama", "options": {"model": "test"}}
    assert task_record.max_loops == 3
    assert task_record.mcp == {
        "servers": ["k8s"],
        "prompts": [{"server": "k8s", "name": "k8s-debug"}],
        "resources": [{"server": "k8s", "uri": "k8s://cluster/default/services"}],
    }
    assert "state" not in task_record.to_dict()
    assert len(events) == 1
    assert events[0].event_type == "task_started"
    assert events[0].session_id == "session-1"
    assert events[0].context_id == "ctx-1"
    assert artifacts == []
    reopened.close()


def test_session_store_maps_interrupted_and_stopped_task_results(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite")
    sessions = SessionStore(store)
    sessions.create_session(session_id="session-1")
    sessions.create_task(
        task_id="task-interrupt",
        session_id="session-1",
        thread_id="thread-interrupt",
        user_input="dangerous",
        model=None,
        max_loops=5,
    )
    sessions.create_task(
        task_id="task-stopped",
        session_id="session-1",
        thread_id="thread-stopped",
        user_input="loop",
        model=None,
        max_loops=5,
    )

    interrupted = sessions.save_task_result(
        task_id="task-interrupt",
        result=RunResult(
            thread_id="thread-interrupt",
            interrupt={"kind": "approval_required"},
            interrupt_message="Approval required.",
        ),
        model=None,
        max_loops=5,
    )
    stopped = sessions.save_task_result(
        task_id="task-stopped",
        result=RunResult(thread_id="thread-stopped", stop_message="Stopped."),
        model=None,
        max_loops=5,
    )

    assert interrupted.status == TaskStatus.INTERRUPTED
    assert interrupted.interrupt == {"kind": "approval_required"}
    assert stopped.status == TaskStatus.STOPPED
    store.close()


def test_session_store_gets_session_by_context_id(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite")
    sessions = SessionStore(store)
    sessions.create_session(session_id="session-1", context_id="ctx-1")
    sessions.create_session(session_id="session-2", context_id="ctx-2")

    match = sessions.get_session_by_context_id("ctx-1")
    missing = sessions.get_session_by_context_id("missing-ctx")

    assert match is not None
    assert match.session_id == "session-1"
    assert match.context_id == "ctx-1"
    assert missing is None
    store.close()


def test_session_store_marks_running_and_failed_tasks(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite")
    sessions = SessionStore(store)
    sessions.create_session(session_id="session-1")
    task = sessions.create_task(
        task_id="task-running",
        session_id="session-1",
        thread_id="thread-running",
        user_input="hello",
        model={"provider": "ollama", "options": {"model": "test"}},
        max_loops=2,
        mcp={"servers": ["k8s"]},
    )

    running = sessions.mark_task_running(task.task_id)
    failed = sessions.mark_task_failed(
        task_id=task.task_id,
        error_code="runtime_error",
        error_message="model unavailable",
    )

    assert running.status == TaskStatus.RUNNING
    assert running.final_answer is None
    assert running.to_dict()["error"] is None
    assert failed.status == TaskStatus.FAILED
    assert failed.error_code == "runtime_error"
    assert failed.error_message == "model unavailable"
    assert failed.to_dict()["error"] == {"code": "runtime_error", "message": "model unavailable"}
    store.close()


def test_session_store_marks_cancel_requested_and_canceled_tasks(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite")
    sessions = SessionStore(store)
    sessions.create_session(session_id="session-1")
    task = sessions.create_task(
        task_id="task-1",
        session_id="session-1",
        thread_id="thread-1",
        user_input="hello",
        model=None,
        max_loops=None,
    )

    cancel_requested = sessions.mark_task_cancel_requested(
        task.task_id,
        stop_message="Task canceled: operator requested",
    )
    canceled = sessions.mark_task_canceled(task.task_id, stop_message="Task canceled: operator requested")

    assert cancel_requested.status == TaskStatus.CANCEL_REQUESTED
    assert cancel_requested.stop_message == "Task canceled: operator requested"
    assert canceled.status == TaskStatus.CANCELED
    assert canceled.stop_message == "Task canceled: operator requested"
    store.close()


def test_session_store_save_task_result_clears_previous_error(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite")
    sessions = SessionStore(store)
    sessions.create_session(session_id="session-1")
    sessions.create_task(
        task_id="task-1",
        session_id="session-1",
        thread_id="thread-1",
        user_input="hello",
        model=None,
        max_loops=None,
    )

    sessions.mark_task_failed(
        task_id="task-1",
        error_code="runtime_error",
        error_message="temporary failure",
    )
    completed = sessions.save_task_result(
        task_id="task-1",
        result=RunResult(thread_id="thread-1", final_answer="done"),
        model=None,
        max_loops=None,
    )

    assert completed.status == TaskStatus.COMPLETED
    assert completed.error_code is None
    assert completed.error_message is None
    assert completed.to_dict()["error"] is None
    store.close()


def test_session_store_persists_retry_lineage(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite")
    sessions = SessionStore(store)
    sessions.create_session(session_id="session-1")
    original = sessions.create_task(
        task_id="task-1",
        session_id="session-1",
        thread_id="task:task-1:attempt:1",
        user_input="hello",
        model=None,
        max_loops=None,
        attempt=1,
    )
    retry = sessions.create_task(
        task_id="task-2",
        session_id="session-1",
        thread_id="task:task-2:attempt:2",
        root_task_id=original.root_task_id,
        retry_of_task_id=original.task_id,
        user_input=original.input,
        model=None,
        max_loops=None,
        attempt=2,
    )

    chain = sessions.list_task_retries("task-1")

    assert original.root_task_id == "task-1"
    assert original.retry_of_task_id is None
    assert retry.root_task_id == "task-1"
    assert retry.retry_of_task_id == "task-1"
    assert [task.task_id for task in chain] == ["task-1", "task-2"]
    assert retry.to_dict()["root_task_id"] == "task-1"
    assert retry.to_dict()["retry_of_task_id"] == "task-1"
    store.close()


def test_session_store_upserts_task_artifacts(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite")
    sessions = SessionStore(store)
    sessions.create_session(session_id="session-1", context_id="ctx-1")
    sessions.create_task(
        task_id="task-1",
        session_id="session-1",
        thread_id="thread-1",
        user_input="hello",
        model=None,
        max_loops=None,
    )

    artifact = sessions.upsert_task_artifact(
        artifact_id="task-1:final_answer",
        task_id="task-1",
        a2a_artifact_id="final_answer",
        name="Final answer",
        description="Final text answer returned by the agent.",
        parts=[{"text": "done", "mediaType": "text/plain"}],
        metadata={"kind": "final_answer"},
        extensions=[],
    )
    updated = sessions.upsert_task_artifact(
        artifact_id="task-1:final_answer",
        task_id="task-1",
        a2a_artifact_id="final_answer",
        name="Final answer",
        description="Final text answer returned by the agent.",
        parts=[{"text": "updated", "mediaType": "text/plain"}],
        metadata={"kind": "final_answer"},
        extensions=[],
    )
    artifacts = sessions.list_task_artifacts("task-1")

    assert artifact.artifact_id == "task-1:final_answer"
    assert artifact.session_id == "session-1"
    assert artifact.context_id == "ctx-1"
    assert artifact.a2a_artifact_id == "final_answer"
    assert artifact.parts == [{"text": "done", "mediaType": "text/plain"}]
    assert updated.parts == [{"text": "updated", "mediaType": "text/plain"}]
    assert updated.metadata == {"kind": "final_answer"}
    assert updated.extensions == []
    assert len(artifacts) == 1
    assert artifacts[0].to_dict()["parts"] == [{"text": "updated", "mediaType": "text/plain"}]
    store.close()
