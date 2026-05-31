from __future__ import annotations

from fastapi.testclient import TestClient

from mini_agent.api.app import create_app
from mini_agent.api.service import AgentService
from mini_agent.api.session_store import SessionStore
from mini_agent.langgraph_runtime.results import RunResult
from mini_agent.storage import AgentStore


class FakeRuntime:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.started = []
        self.resumed = []
        self.closed = False

    def start(self, user_input, thread_id=None):
        self.started.append((user_input, thread_id))
        response = self.responses.pop(0)
        if response.thread_id == "__generated__":
            return RunResult(
                thread_id=thread_id or "generated-thread",
                final_answer=response.final_answer,
                interrupt=response.interrupt,
                interrupt_message=response.interrupt_message,
                stop_message=response.stop_message,
            )
        return response

    def resume(self, thread_id, approved, reason=None):
        self.resumed.append((thread_id, approved, reason))
        return self.responses.pop(0)

    def close(self):
        self.closed = True


def make_client(tmp_path, runtime):
    store = AgentStore(tmp_path / "agent.sqlite")
    service = AgentService(
        session_store=SessionStore(store),
        runtime_builder=lambda config: runtime,
    )
    return TestClient(create_app(service=service)), store, service


def test_api_health(tmp_path):
    client, store, service = make_client(tmp_path, FakeRuntime([RunResult(thread_id="unused", final_answer="ok")]))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    service.close()
    store.close()


def test_api_start_completed_session_and_get_metadata(tmp_path):
    runtime = FakeRuntime([RunResult(thread_id="__generated__", final_answer="done")])
    client, store, service = make_client(tmp_path, runtime)

    response = client.post("/sessions", json={"input": "hello", "max_loops": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["thread_id"] == "generated-thread"
    assert body["status"] == "completed"
    assert body["final_answer"] == "done"
    assert runtime.started == [("hello", None)]

    metadata = client.get("/sessions/generated-thread")
    assert metadata.status_code == 200
    assert metadata.json()["input"] == "hello"
    assert metadata.json()["status"] == "completed"
    service.close()
    store.close()


def test_api_start_interrupted_session_and_resume(tmp_path):
    runtime = FakeRuntime(
        [
            RunResult(
                thread_id="approval-thread",
                interrupt={"kind": "approval_required"},
                interrupt_message="Approval required.",
            ),
            RunResult(thread_id="approval-thread", final_answer="approved"),
        ]
    )
    client, store, service = make_client(tmp_path, runtime)

    interrupted = client.post("/sessions", json={"input": "run dangerous", "thread_id": "approval-thread"})

    assert interrupted.status_code == 200
    assert interrupted.json()["status"] == "interrupted"
    assert interrupted.json()["interrupt"] == {"kind": "approval_required"}

    resumed = client.post(
        "/sessions/approval-thread/resume",
        json={"approved": True, "reason": "approved by operator"},
    )

    assert resumed.status_code == 200
    assert resumed.json()["status"] == "completed"
    assert resumed.json()["final_answer"] == "approved"
    assert runtime.resumed == [("approval-thread", True, "approved by operator")]
    assert client.get("/sessions/approval-thread").json()["status"] == "completed"
    service.close()
    store.close()


def test_api_unknown_session_returns_404(tmp_path):
    client, store, service = make_client(tmp_path, FakeRuntime([RunResult(thread_id="unused", final_answer="ok")]))

    assert client.get("/sessions/missing").status_code == 404
    assert client.post("/sessions/missing/resume", json={"approved": True}).status_code == 404
    service.close()
    store.close()


def test_api_invalid_resume_payload_returns_422(tmp_path):
    client, store, service = make_client(tmp_path, FakeRuntime([RunResult(thread_id="unused", final_answer="ok")]))

    response = client.post("/sessions/missing/resume", json={"reason": "missing approved"})

    assert response.status_code == 422
    service.close()
    store.close()
