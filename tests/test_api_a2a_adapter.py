from __future__ import annotations

from concurrent.futures import Future

import pytest
from fastapi.testclient import TestClient

from mini_agent.api.a2a import A2AAdapter, A2ASendMessageRequest, create_a2a_router
from mini_agent.api.app import create_app
from mini_agent.api.service import AgentService
from mini_agent.api.session_models import TaskStatus
from mini_agent.api.session_store import SessionStore
from mini_agent.errors import InvalidRequestError, TaskNotFoundError
from mini_agent.langgraph_runtime.results import RunResult
from mini_agent.storage import AgentStore


class FakeRuntime:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.started = []
        self.closed = False

    def start(self, user_input, thread_id=None):
        self.started.append((user_input, thread_id))
        response = self.responses.pop(0)
        if callable(response):
            return response(thread_id)
        return response

    def resume(self, thread_id, approved, reason=None):
        raise RuntimeError("not used")

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


def completed(answer="done"):
    return lambda thread_id: RunResult(thread_id=thread_id, final_answer=answer)


def make_adapter(tmp_path, runtime, *, task_execution_service=None):
    store = AgentStore(tmp_path / "agent.sqlite")
    service = AgentService(
        session_store=SessionStore(store),
        runtime_builder=lambda config: runtime,
        task_execution_service=task_execution_service,
    )
    adapter = A2AAdapter(service=service)
    return adapter, store, service, runtime


def test_a2a_agent_card_declares_local_skeleton_capabilities(tmp_path):
    adapter, store, service, _runtime = make_adapter(tmp_path, FakeRuntime([completed()]))

    card = adapter.get_agent_card()

    assert card["name"] == "Mini Agent Workbench"
    assert card["capabilities"] == {
        "streaming": False,
        "pushNotifications": False,
        "extendedAgentCard": False,
    }
    assert card["securitySchemes"] == {}
    assert card["security"] == []
    assert card["defaultInputModes"] == ["text/plain"]
    assert card["defaultOutputModes"] == ["text/plain"]
    assert card["skills"][0]["id"] == "agent-task-execution"
    service.close()
    store.close()


def test_a2a_router_is_not_exposed_by_default_app(tmp_path):
    adapter, store, service, _runtime = make_adapter(tmp_path, FakeRuntime([completed()]))

    router = create_a2a_router(adapter)
    client = TestClient(create_app(service=service))

    assert router.routes
    assert client.get("/.well-known/agent-card.json").status_code == 404
    assert client.post("/message:send", json={}).status_code == 404
    service.close()
    store.close()


def test_a2a_routes_are_exposed_when_enabled(tmp_path):
    runtime = FakeRuntime([completed("weather done")])
    store = AgentStore(tmp_path / "agent.sqlite")
    service = AgentService(session_store=SessionStore(store), runtime_builder=lambda config: runtime)
    client = TestClient(create_app(service=service, enable_a2a=True))

    card = client.get("/.well-known/agent-card.json")
    sent = client.post(
        "/message:send",
        json={
            "message": {
                "role": "user",
                "taskId": "task-1",
                "contextId": "ctx-1",
                "parts": [{"text": "weather forecast for Beijing"}],
            }
        },
    )
    fetched = client.get("/tasks/task-1")
    local_fetched = client.get("/api/tasks/task-1")

    assert card.status_code == 200
    assert card.json()["capabilities"]["streaming"] is True
    assert sent.status_code == 200
    assert sent.json()["task"]["status"]["state"] == "TASK_STATE_COMPLETED"
    assert sent.json()["task"]["contextId"] == "ctx-1"
    assert sent.json()["task"]["artifacts"][0]["parts"] == [{"text": "weather done", "mediaType": "text/plain"}]
    assert "thread" not in str(sent.json()).lower()
    assert fetched.status_code == 200
    assert fetched.json()["task"]["id"] == "task-1"
    assert local_fetched.status_code == 200
    assert local_fetched.json()["task_id"] == "task-1"
    assert local_fetched.json()["thread_id"] == "task:task-1:attempt:1"
    service.close()
    store.close()


def test_a2a_routes_map_invalid_message_and_unknown_task_errors(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite")
    service = AgentService(session_store=SessionStore(store), runtime_builder=lambda config: FakeRuntime([completed()]))
    client = TestClient(create_app(service=service, enable_a2a=True))

    invalid = client.post("/message:send", json={"message": {"role": "agent", "parts": [{"text": "hello"}]}})
    missing = client.get("/tasks/missing-task")

    assert invalid.status_code == 400
    assert invalid.json()["detail"] == {"code": "invalid_request", "message": "A2A message role must be 'user'."}
    assert missing.status_code == 404
    assert missing.json()["detail"] == {"code": "task_not_found", "message": "task not found"}
    service.close()
    store.close()


def test_a2a_cancel_route_maps_to_service_boundary(tmp_path):
    executor = ManualTaskExecutionService()
    store = AgentStore(tmp_path / "agent.sqlite")
    service = AgentService(
        session_store=SessionStore(store),
        runtime_builder=lambda config: FakeRuntime([completed("unused")]),
        task_execution_service=executor,
    )
    service.create_session(session_id="session-1", context_id="ctx-1")
    service.start_task("session-1", "hello", task_id="task-1", wait=False)
    client = TestClient(create_app(service=service, enable_a2a=True))

    response = client.post("/tasks/task-1:cancel", json={"reason": "operator requested"})

    assert response.status_code == 200
    assert response.json()["task"]["status"]["state"] == "TASK_STATE_CANCELED"
    assert service.get_task("task-1").status == TaskStatus.CANCELED
    service.close()
    store.close()


def test_a2a_subscribe_route_streams_projected_status_and_artifact_events(tmp_path):
    store = AgentStore(tmp_path / "agent.sqlite")
    service = AgentService(
        session_store=SessionStore(store),
        runtime_builder=lambda config: FakeRuntime([completed("done")]),
    )
    client = TestClient(create_app(service=service, enable_a2a=True))
    client.post(
        "/message:send",
        json={"message": {"role": "user", "taskId": "task-1", "contextId": "ctx-1", "parts": [{"text": "hello"}]}},
    )

    response = client.post("/tasks/task-1:subscribe")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: statusUpdate" in body
    assert "event: artifactUpdate" in body
    assert "TASK_STATE_COMPLETED" in body
    assert "final_answer" in body
    assert "thread" not in body.lower()


def test_a2a_send_message_creates_context_session_task_and_projected_artifact(tmp_path):
    adapter, store, service, runtime = make_adapter(tmp_path, FakeRuntime([completed("weather done")]))
    request = A2ASendMessageRequest.model_validate(
        {
            "message": {
                "role": "user",
                "taskId": "task-1",
                "contextId": "ctx-1",
                "parts": [{"text": "weather forecast for Beijing"}],
                "metadata": {"tenant": "local", "ignored": "secret"},
            },
            "metadata": {"client": "pytest"},
        }
    )

    payload = adapter.send_message(request)

    assert payload["task"]["id"] == "task-1"
    assert payload["task"]["contextId"] == "ctx-1"
    assert payload["task"]["status"]["state"] == "TASK_STATE_COMPLETED"
    assert payload["task"]["artifacts"][0]["artifactId"] == "final_answer"
    assert payload["task"]["artifacts"][0]["parts"] == [{"text": "weather done", "mediaType": "text/plain"}]
    assert "thread" not in str(payload).lower()
    assert runtime.started[0] == ("weather forecast for Beijing", "task:task-1:attempt:1")
    session = service.get_session_by_context_id("ctx-1")
    assert session is not None
    assert session.metadata == {"client": "pytest", "source": "a2a", "tenant": "local"}
    service.close()
    store.close()


def test_a2a_send_message_reuses_existing_context_session(tmp_path):
    adapter, store, service, _runtime = make_adapter(tmp_path, FakeRuntime([completed()]))
    existing = service.create_session(session_id="session-1", context_id="ctx-1")
    request = A2ASendMessageRequest.model_validate(
        {"message": {"role": "user", "taskId": "task-1", "contextId": "ctx-1", "parts": [{"text": "hello"}]}}
    )

    payload = adapter.send_message(request)

    task = service.get_task("task-1")
    assert task is not None
    assert task.session_id == existing.session_id
    assert payload["task"]["contextId"] == "ctx-1"
    assert [session.session_id for session in service.list_sessions()] == ["session-1"]
    service.close()
    store.close()


def test_a2a_send_message_rejects_empty_or_non_user_message(tmp_path):
    adapter, store, service, _runtime = make_adapter(tmp_path, FakeRuntime([completed()]))

    with pytest.raises(InvalidRequestError, match="at least one text part"):
        adapter.send_message(A2ASendMessageRequest.model_validate({"message": {"role": "user", "parts": []}}))

    with pytest.raises(InvalidRequestError, match="role must be 'user'"):
        adapter.send_message(
            A2ASendMessageRequest.model_validate({"message": {"role": "agent", "parts": [{"text": "hello"}]}})
        )

    service.close()
    store.close()


def test_a2a_get_task_and_cancel_task_use_service_boundary(tmp_path):
    executor = ManualTaskExecutionService()
    adapter, store, service, _runtime = make_adapter(
        tmp_path,
        FakeRuntime([completed("unused")]),
        task_execution_service=executor,
    )
    service.create_session(session_id="session-1", context_id="ctx-1")
    service.start_task("session-1", "hello", task_id="task-1", wait=False)

    queued = adapter.get_task("task-1")
    canceled = adapter.cancel_task("task-1", reason="operator requested")

    assert queued["task"]["status"]["state"] == "TASK_STATE_SUBMITTED"
    assert canceled["task"]["status"]["state"] == "TASK_STATE_CANCELED"
    assert service.get_task("task-1").status == TaskStatus.CANCELED
    with pytest.raises(TaskNotFoundError):
        adapter.get_task("missing-task")
    service.close()
    store.close()


def test_a2a_adapter_projects_status_and_artifact_events_without_internal_payloads(tmp_path):
    adapter, store, service, _runtime = make_adapter(tmp_path, FakeRuntime([completed("done")]))
    request = A2ASendMessageRequest.model_validate(
        {"message": {"role": "user", "taskId": "task-1", "contextId": "ctx-1", "parts": [{"text": "hello"}]}}
    )
    adapter.send_message(request)

    projections = adapter.project_task_events("task-1")

    assert [next(iter(projection)) for projection in projections] == [
        "statusUpdate",
        "statusUpdate",
        "artifactUpdate",
        "statusUpdate",
    ]
    assert projections[-1]["statusUpdate"]["status"]["state"] == "TASK_STATE_COMPLETED"
    assert projections[2]["artifactUpdate"]["artifact"]["artifactId"] == "final_answer"
    assert "thread" not in str(projections).lower()
    service.close()
    store.close()
