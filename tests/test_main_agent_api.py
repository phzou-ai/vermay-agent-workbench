from __future__ import annotations

from fastapi.testclient import TestClient

from vermay_agent.api.app import create_app
from vermay_agent.api.service import AgentService
from vermay_agent.api.session_store import SessionStore
from vermay_agent.langgraph_runtime.results import RunResult
from vermay_agent.main_agent import MainAgentCore, MainAgentStore, MessageRecord
from vermay_agent.storage import AgentStore


class FakeRuntime:
    def __init__(self, responses) -> None:
        self.responses = list(responses)

    def start(self, user_input, thread_id=None):
        response = self.responses.pop(0)
        if callable(response):
            return response(thread_id)
        return response

    def resume(self, thread_id, approved, reason=None):
        raise RuntimeError("not used")

    def close(self):
        return None


class FakeLocalMessageResponder:
    def __init__(self) -> None:
        self.calls = []

    def respond(self, messages: list[MessageRecord]) -> list[dict]:
        self.calls.append(messages)
        return [{"kind": "text", "text": "direct answer"}]


def completed(answer="done"):
    return lambda thread_id: RunResult(thread_id=thread_id, final_answer=answer)


def make_client(tmp_path):
    agent_store = AgentStore(tmp_path / "agent.sqlite")
    main_store = MainAgentStore(agent_store)
    core = MainAgentCore(store=main_store, local_message_responder=FakeLocalMessageResponder())
    service = AgentService(
        session_store=SessionStore(agent_store),
        runtime_builder=lambda config: FakeRuntime([completed("unused")]),
    )
    client = TestClient(create_app(service=service, enable_a2a=True, main_agent_core=core))
    return client, agent_store, service, core


def test_main_agent_context_api_lists_messages_and_deletes_context(tmp_path):
    client, agent_store, service, _core = make_client(tmp_path)
    sent = client.post(
        "/message:send",
        json={
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "role": "user",
                    "messageId": "msg-user-1",
                    "parts": [{"kind": "text", "text": "hello"}],
                },
                "metadata": {"executionMode": "message"},
            },
        },
    )
    context_id = sent.json()["result"]["contextId"]

    contexts = client.get("/api/contexts")
    messages = client.get(f"/api/contexts/{context_id}/messages")
    route_decisions = client.get(f"/api/contexts/{context_id}/route-decisions")
    deleted = client.delete(f"/api/contexts/{context_id}", params={"force": "true"})

    assert contexts.status_code == 200
    assert contexts.json()[0]["context_id"] == context_id
    assert messages.status_code == 200
    assert [message["message_id"] for message in messages.json()] == [
        "msg-user-1",
        sent.json()["result"]["messageId"],
    ]
    assert route_decisions.status_code == 200
    assert route_decisions.json()[0]["kind"] == "local_message"
    assert route_decisions.json()[0]["message_id"] == "msg-user-1"
    assert deleted.status_code == 204
    assert client.get(f"/api/contexts/{context_id}").status_code == 404
    service.close()
    agent_store.close()


def test_main_agent_registered_agent_api_crud(tmp_path):
    client, agent_store, service, _core = make_client(tmp_path)

    created = client.post(
        "/api/registered-agents",
        json={
            "agent_id": "agent-child-1",
            "name": "Child agent",
            "card_url": "http://127.0.0.1:9001/.well-known/agent-card.json",
            "card_json": {"name": "Child agent"},
            "enabled": True,
            "metadata": {"team": "local", "keywords": ["sqlite", "kubernetes"]},
        },
    )
    disabled = client.post(
        "/api/registered-agents",
        json={
            "agent_id": "agent-disabled",
            "name": "Disabled agent",
            "card_url": "http://127.0.0.1:9002/.well-known/agent-card.json",
            "enabled": False,
        },
    )
    listed = client.get("/api/registered-agents")
    enabled_only = client.get("/api/registered-agents", params={"enabled_only": "true"})
    fetched = client.get("/api/registered-agents/agent-child-1")
    deleted = client.delete("/api/registered-agents/agent-child-1")
    missing = client.get("/api/registered-agents/agent-child-1")

    assert created.status_code == 200
    assert created.json()["agent_id"] == "agent-child-1"
    assert created.json()["card_json"] == {"name": "Child agent"}
    assert created.json()["metadata"] == {"team": "local", "keywords": ["sqlite", "kubernetes"]}
    assert disabled.status_code == 200
    assert listed.status_code == 200
    assert {agent["agent_id"] for agent in listed.json()} == {"agent-child-1", "agent-disabled"}
    assert enabled_only.status_code == 200
    assert [agent["agent_id"] for agent in enabled_only.json()] == ["agent-child-1"]
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Child agent"
    assert deleted.status_code == 204
    assert missing.status_code == 404
    service.close()
    agent_store.close()


def test_main_agent_registered_agent_refresh_card(tmp_path, monkeypatch):
    client, agent_store, service, core = make_client(tmp_path)
    core.store.upsert_registered_agent(
        agent_id="agent-sql",
        name="SQL Agent",
        card_url="http://127.0.0.1:9001/.well-known/agent-card.json",
        card_json={"name": "stale"},
        metadata={"keywords": ["manual"]},
    )

    monkeypatch.setattr(
        "vermay_agent.api.app.fetch_agent_card",
        lambda card_url: {
            "name": "SQL Agent",
            "skills": [{"id": "sqlite-debug", "tags": ["sqlite", "database"]}],
            "url": card_url,
        },
    )

    refreshed = client.post("/api/registered-agents/agent-sql/refresh-card")

    assert refreshed.status_code == 200
    assert refreshed.json()["card_json"] == {
        "name": "SQL Agent",
        "skills": [{"id": "sqlite-debug", "tags": ["sqlite", "database"]}],
        "url": "http://127.0.0.1:9001/.well-known/agent-card.json",
    }
    assert refreshed.json()["metadata"] == {"keywords": ["manual"]}
    service.close()
    agent_store.close()


def test_main_agent_registered_agent_refresh_card_missing_agent(tmp_path):
    client, agent_store, service, _core = make_client(tmp_path)

    missing = client.post("/api/registered-agents/missing-agent/refresh-card")

    assert missing.status_code == 404
    assert missing.json()["code"] == "registered_agent_not_found"
    service.close()
    agent_store.close()
