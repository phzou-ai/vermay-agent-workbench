from __future__ import annotations

import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass

from fastapi.testclient import TestClient

from vermay_agent.api.app import create_app
from vermay_agent.api.service import AgentService
from vermay_agent.api.session_store import SessionStore
from vermay_agent.app_factory import RuntimeFactoryConfig
from vermay_agent.langgraph_runtime.results import RunResult
from vermay_agent.mcp.transport import MCPTransportError
from vermay_agent.storage import AgentStore


SESSION_RESPONSE_KEYS = {
    "session_id",
    "context_id",
    "title",
    "status",
    "metadata",
    "created_at",
    "updated_at",
}

TASK_RESPONSE_KEYS = {
    "task_id",
    "session_id",
    "thread_id",
    "root_task_id",
    "retry_of_task_id",
    "status",
    "input",
    "attempt",
    "final_answer",
    "interrupt",
    "interrupt_message",
    "stop_message",
    "error",
    "model",
    "max_loops",
    "mcp",
    "created_at",
    "updated_at",
}


class FakeRuntime:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.started = []
        self.resumed = []
        self.closed = False

    def start(self, user_input, thread_id=None):
        self.started.append((user_input, thread_id))
        return self._next(thread_id)

    def resume(self, thread_id, approved, reason=None):
        self.resumed.append((thread_id, approved, reason))
        return self._next(thread_id)

    def close(self):
        self.closed = True

    def _next(self, thread_id):
        response = self.responses.pop(0)
        if callable(response):
            return response(thread_id)
        return response


class BlockingRuntime:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.closed = False

    def start(self, user_input, thread_id=None):
        self.started.set()
        self.release.wait(timeout=5)
        return RunResult(thread_id=thread_id, final_answer="done")

    def resume(self, thread_id, approved, reason=None):
        self.started.set()
        self.release.wait(timeout=5)
        return RunResult(thread_id=thread_id, final_answer="resumed")

    def close(self):
        self.closed = True


def completed(answer="done"):
    return lambda thread_id: RunResult(thread_id=thread_id, final_answer=answer)


def interrupted():
    return lambda thread_id: RunResult(
        thread_id=thread_id,
        interrupt={"kind": "approval_required"},
        interrupt_message="Approval required.",
    )


@dataclass
class FailingService:
    exc: Exception
    closed: bool = False

    def create_session(self, *args, **kwargs):
        raise self.exc

    def list_sessions(self):
        return []

    def start_task(self, *args, **kwargs):
        raise self.exc

    def resume_task(self, *args, **kwargs):
        raise self.exc

    def cancel_task(self, *args, **kwargs):
        raise self.exc

    def retry_task(self, *args, **kwargs):
        raise self.exc

    def get_session(self, session_id):
        return None

    def get_task(self, task_id):
        return None

    def list_task_events(self, task_id):
        raise self.exc

    def close(self):
        self.closed = True


class ManualTaskExecutionService:
    def __init__(self) -> None:
        self.submitted = []

    def submit(self, func, *args):
        self.submitted.append((func, args))
        future = Future()
        future.set_result(None)
        return future

    def shutdown(self):
        return None

    def run_next(self):
        func, args = self.submitted.pop(0)
        return func(*args)


def make_client(tmp_path, runtime, *, task_execution_service=None):
    store = AgentStore(tmp_path / "agent.sqlite")
    service = AgentService(
        session_store=SessionStore(store),
        runtime_builder=lambda config: runtime,
        task_execution_service=task_execution_service,
    )
    return TestClient(create_app(service=service)), store, service


def wait_for_task_status(client, task_id, status, *, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/tasks/{task_id}")
        if response.status_code == 200 and response.json()["status"] == status:
            return response.json()
        time.sleep(0.01)
    response = client.get(f"/api/tasks/{task_id}")
    raise AssertionError(f"task {task_id} did not reach {status}; current={response.json() if response.status_code == 200 else response.status_code}")


def test_api_health(tmp_path):
    client, store, service = make_client(tmp_path, FakeRuntime([completed()]))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    service.close()
    store.close()


def test_local_api_routes_are_under_api_prefix(tmp_path):
    client, store, service = make_client(tmp_path, FakeRuntime([completed()]))

    assert client.get("/sessions").status_code == 404
    assert client.get("/tasks/task-1").status_code == 404

    service.close()
    store.close()


def test_api_create_session_and_get_metadata(tmp_path):
    client, store, service = make_client(tmp_path, FakeRuntime([completed()]))

    response = client.post(
        "/api/sessions",
        json={"session_id": "session-1", "context_id": "ctx-1", "title": "Ops", "metadata": {"source": "test"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == SESSION_RESPONSE_KEYS
    assert body["session_id"] == "session-1"
    assert body["context_id"] == "ctx-1"
    assert body["title"] == "Ops"
    assert body["status"] == "active"
    assert body["metadata"] == {"source": "test"}

    metadata = client.get("/api/sessions/session-1")
    assert metadata.status_code == 200
    assert metadata.json()["session_id"] == "session-1"
    assert client.get("/api/sessions").json()[0]["session_id"] == "session-1"
    service.close()
    store.close()


def test_api_start_completed_task_and_get_metadata(tmp_path):
    runtime = FakeRuntime([completed("done")])
    client, store, service = make_client(tmp_path, runtime)
    client.post("/api/sessions", json={"session_id": "session-1"})

    response = client.post("/api/sessions/session-1/tasks", json={"input": "hello", "task_id": "task-1", "max_loops": 2})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == TASK_RESPONSE_KEYS
    assert body["task_id"] == "task-1"
    assert body["session_id"] == "session-1"
    assert body["thread_id"] == "task:task-1:attempt:1"
    assert body["root_task_id"] == "task-1"
    assert body["retry_of_task_id"] is None
    assert body["status"] == "completed"
    assert body["input"] == "hello"
    assert body["final_answer"] == "done"
    assert body["error"] is None
    assert body["max_loops"] == 2
    assert body["model"] is None
    assert body["mcp"] is None
    assert runtime.started[0] == ("hello", body["thread_id"])

    metadata = client.get("/api/tasks/task-1")
    assert metadata.status_code == 200
    assert set(metadata.json()) == TASK_RESPONSE_KEYS
    assert metadata.json()["input"] == "hello"
    assert metadata.json()["status"] == "completed"
    events = client.get("/api/tasks/task-1/events")
    assert events.status_code == 200
    assert [event["event_type"] for event in events.json()] == [
        "task_created",
        "task_started",
        "task_artifact_created",
        "task_completed",
    ]
    service.close()
    store.close()


def test_api_start_task_wait_false_returns_queued_then_completed(tmp_path):
    runtime = FakeRuntime([completed("done")])
    client, store, service = make_client(tmp_path, runtime)
    client.post("/api/sessions", json={"session_id": "session-1"})

    response = client.post(
        "/api/sessions/session-1/tasks",
        json={"input": "hello", "task_id": "task-1", "wait": False},
    )
    completed_task = wait_for_task_status(client, "task-1", "completed")
    events = client.get("/api/tasks/task-1/events").json()

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert completed_task["final_answer"] == "done"
    assert [event["event_type"] for event in events] == [
        "task_created",
        "task_queued",
        "task_started",
        "task_artifact_created",
        "task_completed",
    ]
    service.close()
    store.close()


def test_api_task_stream_replays_persisted_events_and_closes_on_terminal_status(tmp_path):
    runtime = FakeRuntime([completed("done")])
    client, store, service = make_client(tmp_path, runtime)
    client.post("/api/sessions", json={"session_id": "session-1"})
    client.post("/api/sessions/session-1/tasks", json={"input": "hello", "task_id": "task-1"})

    with client.stream("GET", "/api/tasks/task-1/stream") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "id: 1\n" in body
    assert "event: task_created\n" in body
    assert "event: task_started\n" in body
    assert "event: task_artifact_created\n" in body
    assert "event: task_completed\n" in body
    assert '"done"' not in body
    service.close()
    store.close()


def test_api_task_stream_respects_after_event_cursor(tmp_path):
    runtime = FakeRuntime([completed("done")])
    client, store, service = make_client(tmp_path, runtime)
    client.post("/api/sessions", json={"session_id": "session-1"})
    client.post("/api/sessions/session-1/tasks", json={"input": "hello", "task_id": "task-1"})

    with client.stream("GET", "/api/tasks/task-1/stream?after=1") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: task_created\n" not in body
    assert "event: task_started\n" in body
    assert "event: task_artifact_created\n" in body
    assert "event: task_completed\n" in body
    service.close()
    store.close()


def test_api_task_stream_waits_for_live_terminal_event(tmp_path):
    runtime = BlockingRuntime()
    client, store, service = make_client(tmp_path, runtime)
    client.post("/api/sessions", json={"session_id": "session-1"})
    client.post("/api/sessions/session-1/tasks", json={"input": "hello", "task_id": "task-1", "wait": False})
    assert runtime.started.wait(timeout=5)
    current_events = client.get("/api/tasks/task-1/events").json()
    after = current_events[-1]["event_id"]

    def release_runtime() -> None:
        time.sleep(0.05)
        runtime.release.set()

    release_thread = threading.Thread(target=release_runtime)
    release_thread.start()
    with client.stream("GET", f"/api/tasks/task-1/stream?after={after}") as response:
        body = "".join(response.iter_text())
    release_thread.join(timeout=5)

    assert response.status_code == 200
    assert "event: task_artifact_created\n" in body
    assert "event: task_completed\n" in body
    assert wait_for_task_status(client, "task-1", "completed")["final_answer"] == "done"
    service.close()
    store.close()


def test_api_cancel_queued_task(tmp_path):
    executor = ManualTaskExecutionService()
    client, store, service = make_client(tmp_path, FakeRuntime([completed("done")]), task_execution_service=executor)
    client.post("/api/sessions", json={"session_id": "session-1"})
    client.post("/api/sessions/session-1/tasks", json={"input": "hello", "task_id": "task-1", "wait": False})

    response = client.post("/api/tasks/task-1/cancel", json={"reason": "operator requested"})
    executor.run_next()

    assert response.status_code == 200
    assert response.json()["status"] == "canceled"
    assert response.json()["stop_message"] == "Task canceled: operator requested"
    assert client.get("/api/tasks/task-1").json()["status"] == "canceled"
    assert [event["event_type"] for event in client.get("/api/tasks/task-1/events").json()] == [
        "task_created",
        "task_queued",
        "task_cancel_requested",
        "task_cancelled",
    ]
    service.close()
    store.close()


def test_api_cancel_running_task_records_request_then_terminal_cancel(tmp_path):
    runtime = BlockingRuntime()
    client, store, service = make_client(tmp_path, runtime)
    client.post("/api/sessions", json={"session_id": "session-1"})
    client.post("/api/sessions/session-1/tasks", json={"input": "hello", "task_id": "task-1", "wait": False})
    assert runtime.started.wait(timeout=5)

    response = client.post("/api/tasks/task-1/cancel", json={"reason": "operator requested"})
    runtime.release.set()
    canceled = wait_for_task_status(client, "task-1", "canceled")

    assert response.status_code == 200
    assert response.json()["status"] == "cancel_requested"
    assert canceled["status"] == "canceled"
    assert canceled["final_answer"] is None
    service.close()
    store.close()


def test_api_cancel_terminal_task_returns_409(tmp_path):
    client, store, service = make_client(tmp_path, FakeRuntime([completed("done")]))
    client.post("/api/sessions", json={"session_id": "session-1"})
    client.post("/api/sessions/session-1/tasks", json={"input": "hello", "task_id": "task-1"})

    response = client.post("/api/tasks/task-1/cancel", json={})

    assert response.status_code == 409
    assert "already terminal" in response.json()["detail"]
    service.close()
    store.close()


def test_api_retry_completed_task_creates_new_task(tmp_path):
    runtime = FakeRuntime([completed("first"), completed("retry")])
    client, store, service = make_client(tmp_path, runtime)
    client.post("/api/sessions", json={"session_id": "session-1"})
    client.post("/api/sessions/session-1/tasks", json={"input": "hello", "task_id": "task-1"})

    response = client.post("/api/tasks/task-1/retry", json={"task_id": "task-2", "reason": "try again"})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == TASK_RESPONSE_KEYS
    assert body["task_id"] == "task-2"
    assert body["thread_id"] == "task:task-2:attempt:2"
    assert body["root_task_id"] == "task-1"
    assert body["retry_of_task_id"] == "task-1"
    assert body["attempt"] == 2
    assert body["input"] == "hello"
    assert body["final_answer"] == "retry"
    assert [event["event_type"] for event in client.get("/api/tasks/task-1/events").json()] == [
        "task_created",
        "task_started",
        "task_artifact_created",
        "task_completed",
        "task_retry_requested",
        "task_retried",
    ]
    assert [event["event_type"] for event in client.get("/api/tasks/task-2/events").json()] == [
        "task_created",
        "task_started",
        "task_artifact_created",
        "task_completed",
    ]
    service.close()
    store.close()


def test_api_retry_wait_false_returns_queued_then_completed(tmp_path):
    runtime = FakeRuntime([completed("first"), completed("retry")])
    client, store, service = make_client(tmp_path, runtime)
    client.post("/api/sessions", json={"session_id": "session-1"})
    client.post("/api/sessions/session-1/tasks", json={"input": "hello", "task_id": "task-1"})

    response = client.post("/api/tasks/task-1/retry", json={"task_id": "task-2", "wait": False})
    completed_task = wait_for_task_status(client, "task-2", "completed")

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert response.json()["attempt"] == 2
    assert completed_task["final_answer"] == "retry"
    service.close()
    store.close()


def test_api_retry_active_task_returns_409(tmp_path):
    runtime = BlockingRuntime()
    client, store, service = make_client(tmp_path, runtime)
    client.post("/api/sessions", json={"session_id": "session-1"})
    client.post("/api/sessions/session-1/tasks", json={"input": "hello", "task_id": "task-1", "wait": False})
    assert runtime.started.wait(timeout=5)

    response = client.post("/api/tasks/task-1/retry", json={"task_id": "task-2"})

    assert response.status_code == 409
    assert "not retryable" in response.json()["detail"]
    runtime.release.set()
    wait_for_task_status(client, "task-1", "completed")
    service.close()
    store.close()


def test_api_start_task_accepts_mcp_selection_and_persists_metadata(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite")
    runtime = FakeRuntime([completed()])
    built_configs: list[RuntimeFactoryConfig] = []

    def build(config):
        built_configs.append(config)
        return runtime

    service = AgentService(session_store=SessionStore(store), runtime_builder=build)
    client = TestClient(create_app(service=service))
    client.post("/api/sessions", json={"session_id": "session-1"})

    response = client.post(
        "/api/sessions/session-1/tasks",
        json={
            "input": "debug service",
            "task_id": "task-1",
            "mcp": {
                "servers": ["k8s"],
                "prompts": [
                    {
                        "server": "k8s",
                        "name": "k8s-debug",
                        "arguments": {"service": "phzou-core"},
                    }
                ],
                "resources": [{"server": "k8s", "uri": "k8s://cluster/default/services"}],
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["mcp"] == {
        "servers": ["k8s"],
        "prompts": [{"server": "k8s", "name": "k8s-debug", "arguments": {"service": "phzou-core"}}],
        "resources": [{"server": "k8s", "uri": "k8s://cluster/default/services"}],
    }
    assert built_configs[-1].mcp_servers == ("k8s",)
    assert built_configs[-1].mcp_prompts == ("k8s:k8s-debug?service=phzou-core",)
    assert built_configs[-1].mcp_resources == ("k8s:k8s://cluster/default/services",)

    metadata = client.get("/api/tasks/task-1")
    assert metadata.status_code == 200
    assert metadata.json()["mcp"] == {
        "servers": ["k8s"],
        "prompts": [{"server": "k8s", "name": "k8s-debug", "arguments": {"service": "phzou-core"}}],
        "resources": [{"server": "k8s", "uri": "k8s://cluster/default/services"}],
    }


def test_api_start_task_accepts_configured_model_name(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite")
    runtime = FakeRuntime([completed()])
    built_configs: list[RuntimeFactoryConfig] = []

    def build(config):
        built_configs.append(config)
        return runtime

    service = AgentService(session_store=SessionStore(store), runtime_builder=build)
    client = TestClient(create_app(service=service))
    client.post("/api/sessions", json={"session_id": "session-1"})

    response = client.post(
        "/api/sessions/session-1/tasks",
        json={"input": "hello", "task_id": "task-1", "model": "qwen_vllm"},
    )

    assert response.status_code == 200
    assert response.json()["model"]["provider"] == "openai_compatible"
    assert response.json()["model"]["options"]["model"] == "qwen"
    assert built_configs[-1].model.provider == "openai_compatible"
    service.close()
    store.close()
    service.close()
    store.close()


def test_api_mcp_prompt_must_reference_selected_server(tmp_path):
    client, store, service = make_client(tmp_path, FakeRuntime([completed()]))
    client.post("/api/sessions", json={"session_id": "session-1"})

    response = client.post(
        "/api/sessions/session-1/tasks",
        json={
            "input": "debug service",
            "mcp": {
                "servers": ["docs"],
                "prompts": [{"server": "k8s", "name": "k8s-debug"}],
            },
        },
    )

    assert response.status_code == 400
    assert "unselected server" in response.json()["detail"]
    service.close()
    store.close()


def test_api_start_interrupted_task_and_resume(tmp_path):
    runtime = FakeRuntime([interrupted(), completed("approved")])
    client, store, service = make_client(tmp_path, runtime)
    client.post("/api/sessions", json={"session_id": "session-1"})

    interrupted_response = client.post(
        "/api/sessions/session-1/tasks",
        json={"input": "run dangerous", "task_id": "task-1"},
    )

    assert interrupted_response.status_code == 200
    assert set(interrupted_response.json()) == TASK_RESPONSE_KEYS
    assert interrupted_response.json()["status"] == "interrupted"
    assert interrupted_response.json()["input"] == "run dangerous"
    assert interrupted_response.json()["interrupt"] == {"kind": "approval_required"}
    assert interrupted_response.json()["error"] is None

    resumed = client.post(
        "/api/tasks/task-1/resume",
        json={"approved": True, "reason": "approved by operator"},
    )

    assert resumed.status_code == 200
    assert set(resumed.json()) == TASK_RESPONSE_KEYS
    assert resumed.json()["status"] == "completed"
    assert resumed.json()["input"] == "run dangerous"
    assert resumed.json()["final_answer"] == "approved"
    assert resumed.json()["error"] is None
    assert runtime.resumed == [("task:task-1:attempt:1", True, "approved by operator")]
    assert client.get("/api/tasks/task-1").json()["status"] == "completed"
    service.close()
    store.close()


def test_api_duplicate_task_start_returns_409(tmp_path):
    runtime = FakeRuntime([completed(), completed("second")])
    client, store, service = make_client(tmp_path, runtime)
    client.post("/api/sessions", json={"session_id": "session-1"})

    first = client.post("/api/sessions/session-1/tasks", json={"input": "hello", "task_id": "task-1"})
    second = client.post("/api/sessions/session-1/tasks", json={"input": "hello again", "task_id": "task-1"})

    assert first.status_code == 200
    assert second.status_code == 409
    assert "task already exists" in second.json()["detail"]
    service.close()
    store.close()


def test_api_resume_completed_task_returns_409(tmp_path):
    runtime = FakeRuntime([completed()])
    client, store, service = make_client(tmp_path, runtime)
    client.post("/api/sessions", json={"session_id": "session-1"})
    first = client.post("/api/sessions/session-1/tasks", json={"input": "hello", "task_id": "task-1"})

    resumed = client.post("/api/tasks/task-1/resume", json={"approved": True})

    assert first.status_code == 200
    assert resumed.status_code == 409
    assert "not waiting for resume" in resumed.json()["detail"]
    service.close()
    store.close()


def test_api_unknown_session_or_task_returns_404(tmp_path):
    client, store, service = make_client(tmp_path, FakeRuntime([completed()]))

    assert client.get("/api/sessions/missing").status_code == 404
    assert client.post("/api/sessions/missing/tasks", json={"input": "hello"}).status_code == 404
    assert client.get("/api/tasks/missing").status_code == 404
    assert client.get("/api/tasks/missing/events").status_code == 404
    assert client.post("/api/tasks/missing/resume", json={"approved": True}).status_code == 404
    assert client.post("/api/tasks/missing/cancel", json={}).status_code == 404
    assert client.post("/api/tasks/missing/retry", json={}).status_code == 404
    service.close()
    store.close()


def test_api_invalid_resume_payload_returns_422(tmp_path):
    client, store, service = make_client(tmp_path, FakeRuntime([completed()]))

    response = client.post("/api/tasks/missing/resume", json={"reason": "missing approved"})

    assert response.status_code == 422
    service.close()
    store.close()


def test_api_start_task_maps_value_error_to_400():
    client = TestClient(create_app(service=FailingService(ValueError("bad model config"))))

    response = client.post("/api/sessions/session-1/tasks", json={"input": "hello"})

    assert response.status_code == 400
    assert response.json()["detail"] == "bad model config"


def test_api_start_task_maps_mcp_transport_error_to_400():
    client = TestClient(create_app(service=FailingService(MCPTransportError("MCP server failed"))))

    response = client.post("/api/sessions/session-1/tasks", json={"input": "hello"})

    assert response.status_code == 400
    assert response.json()["detail"] == "MCP server failed"


def test_api_resume_maps_runtime_error_to_safe_500():
    client = TestClient(create_app(service=FailingService(RuntimeError("secret internal detail"))))

    response = client.post("/api/tasks/task-1/resume", json={"approved": True})

    assert response.status_code == 500
    assert response.json()["detail"] == "agent runtime error"


def test_create_app_does_not_close_injected_service_on_shutdown():
    service = FailingService(ValueError("unused"))

    with TestClient(create_app(service=service)) as client:
        assert client.get("/health").status_code == 200

    assert service.closed is False
