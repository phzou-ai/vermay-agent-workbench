from __future__ import annotations

import json
from dataclasses import dataclass

from vermay_agent.main_agent.models import MainAgentRequest, MessageRole, RegisteredAgentRecord
from vermay_agent.main_agent.remote_agent import DirectA2ARemoteAgentClient


@dataclass
class FakeResponse:
    payload: dict

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_direct_a2a_remote_agent_send_message_uses_rpc(monkeypatch):
    captured = []

    def fake_urlopen(request, timeout):
        captured.append((request, timeout))
        return FakeResponse(
            {
                "jsonrpc": "2.0",
                "id": "delegate-msg-1",
                "result": {
                    "kind": "message",
                    "contextId": "remote-ctx-1",
                    "messageId": "remote-msg-1",
                    "parts": [{"kind": "text", "text": "remote answer"}],
                },
            }
        )

    monkeypatch.setattr("vermay_agent.main_agent.remote_agent.urlopen", fake_urlopen)
    client = DirectA2ARemoteAgentClient(timeout_seconds=3.0)

    result = client.send_message(
        agent=_registered_agent(),
        request=MainAgentRequest(
            context_id="ctx-1",
            message_id="msg-1",
            role=MessageRole.USER,
            parts=[{"kind": "text", "text": "delegate"}],
            metadata={"executionMode": "task"},
        ),
        context_id="ctx-1",
        message_id="msg-1",
    )

    request, timeout = captured[0]
    payload = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "http://child-agent.local/rpc"
    assert request.get_method() == "POST"
    assert timeout == 3.0
    assert payload["method"] == "SendMessage"
    assert payload["params"]["message"]["contextId"] == "ctx-1"
    assert payload["params"]["metadata"] == {
        "delegatedBy": "vermay-main-agent",
        "sourceContextId": "ctx-1",
        "executionMode": "task",
    }
    assert result.kind == "message"
    assert result.message_id == "remote-msg-1"


def test_direct_a2a_remote_agent_get_task_uses_rpc(monkeypatch):
    captured = []

    def fake_urlopen(request, timeout):
        captured.append((request, timeout))
        return FakeResponse(
            {
                "jsonrpc": "2.0",
                "id": "get-remote-task-remote-task-1",
                "result": {
                    "kind": "task",
                    "id": "remote-task-1",
                    "contextId": "remote-ctx-1",
                    "status": {"state": "completed"},
                    "artifacts": [{"artifactId": "final"}],
                },
            }
        )

    monkeypatch.setattr("vermay_agent.main_agent.remote_agent.urlopen", fake_urlopen)
    client = DirectA2ARemoteAgentClient(timeout_seconds=3.0)

    snapshot = client.get_task(agent=_registered_agent(), task_id="remote-task-1")

    request, timeout = captured[0]
    payload = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "http://child-agent.local/rpc"
    assert request.get_method() == "POST"
    assert timeout == 3.0
    assert payload == {
        "jsonrpc": "2.0",
        "id": "get-remote-task-remote-task-1",
        "method": "GetTask",
        "params": {"id": "remote-task-1"},
    }
    assert snapshot.task_id == "remote-task-1"
    assert snapshot.status == "completed"


def test_direct_a2a_remote_agent_cancel_task_uses_rpc(monkeypatch):
    captured = []

    def fake_urlopen(request, timeout):
        captured.append((request, timeout))
        return FakeResponse(
            {
                "jsonrpc": "2.0",
                "id": "cancel-remote-task-remote-task-1",
                "result": {
                    "kind": "task",
                    "id": "remote-task-1",
                    "contextId": "remote-ctx-1",
                    "status": {"state": "canceled"},
                },
            }
        )

    monkeypatch.setattr("vermay_agent.main_agent.remote_agent.urlopen", fake_urlopen)
    client = DirectA2ARemoteAgentClient(timeout_seconds=3.0)

    snapshot = client.cancel_task(
        agent=_registered_agent(),
        task_id="remote-task-1",
        reason="operator",
    )

    request, timeout = captured[0]
    payload = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "http://child-agent.local/rpc"
    assert request.get_method() == "POST"
    assert timeout == 3.0
    assert payload == {
        "jsonrpc": "2.0",
        "id": "cancel-remote-task-remote-task-1",
        "method": "CancelTask",
        "params": {"id": "remote-task-1", "reason": "operator"},
    }
    assert snapshot.task_id == "remote-task-1"
    assert snapshot.status == "canceled"


def _registered_agent() -> RegisteredAgentRecord:
    return RegisteredAgentRecord(
        agent_id="child-agent",
        name="Child Agent",
        card_url="http://child-agent.local/.well-known/agent-card.json",
        card_json={},
        enabled=True,
        metadata={},
        created_at="2026-06-08T00:00:00Z",
        updated_at="2026-06-08T00:00:00Z",
    )
