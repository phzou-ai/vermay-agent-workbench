from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient

from vermay_agent.api.app import create_app
from vermay_agent.api.service import AgentService
from vermay_agent.api.session_store import SessionStore
from vermay_agent.langgraph_runtime.results import RunResult
from vermay_agent.storage import AgentStore


class FakeRuntime:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.closed = False

    def start(self, user_input, thread_id=None):
        response = self.responses.pop(0)
        if callable(response):
            return response(thread_id)
        return response

    def resume(self, thread_id, approved, reason=None):
        raise RuntimeError("not used")

    def close(self):
        self.closed = True


@dataclass
class InjectedService:
    closed: bool = False

    def close(self):
        self.closed = True


def completed(answer="done"):
    return lambda thread_id: RunResult(thread_id=thread_id, final_answer=answer)


def make_client(tmp_path, runtime):
    store = AgentStore(tmp_path / "agent.sqlite")
    service = AgentService(
        session_store=SessionStore(store),
        runtime_builder=lambda config: runtime,
    )
    return TestClient(create_app(service=service)), store, service


def test_api_health(tmp_path):
    client, store, service = make_client(tmp_path, FakeRuntime([completed()]))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    service.close()
    store.close()


def test_legacy_local_rest_routes_are_not_exposed(tmp_path):
    client, store, service = make_client(tmp_path, FakeRuntime([completed()]))

    legacy_requests = [
        ("post", "/api/sessions", {"json": {"session_id": "session-1"}}),
        ("get", "/api/sessions", {}),
        ("get", "/api/sessions/session-1", {}),
        ("delete", "/api/sessions/session-1", {}),
        ("post", "/api/sessions/session-1/tasks", {"json": {"input": "hello"}}),
        ("get", "/api/tasks/task-1", {}),
        ("get", "/api/tasks/task-1/events", {}),
        ("get", "/api/tasks/task-1/artifacts", {}),
        ("get", "/api/tasks/task-1/artifacts/task-1:final_answer", {}),
        ("get", "/api/tasks/task-1/stream", {}),
        ("post", "/api/tasks/task-1/resume", {"json": {"approved": True}}),
        ("post", "/api/tasks/task-1/cancel", {"json": {"reason": "operator"}}),
        ("post", "/api/tasks/task-1/retry", {"json": {"reason": "try again"}}),
    ]

    for method, path, kwargs in legacy_requests:
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 404, path
        assert response.json() == {"detail": "Not Found"}

    service.close()
    store.close()


def test_unprefixed_local_rest_routes_are_not_exposed(tmp_path):
    client, store, service = make_client(tmp_path, FakeRuntime([completed()]))

    assert client.get("/sessions").status_code == 404
    assert client.get("/sessions").json() == {"detail": "Not Found"}
    assert client.get("/tasks/task-1").status_code == 404

    service.close()
    store.close()


def test_create_app_does_not_close_injected_service_on_shutdown():
    service = InjectedService()

    with TestClient(create_app(service=service)) as client:
        assert client.get("/health").status_code == 200

    assert service.closed is False
