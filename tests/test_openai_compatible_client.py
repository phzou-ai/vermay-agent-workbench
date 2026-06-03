from __future__ import annotations

import json

from mini_agent.model_clients.openai_compatible import OpenAICompatibleModelClient
from mini_agent.types import Message


class FakeResponse:
    def __init__(self, body: dict) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.body).encode("utf-8")


def test_openai_compatible_client_omits_tools_when_no_tools(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"choices": [{"message": {"content": "done"}}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = OpenAICompatibleModelClient(model="gpt-4o", base_url="https://api.openai.com/v1")
    response = client.invoke([Message(role="user", content="hello")], tools=[])

    assert response.content == "done"
    assert "tools" not in captured["payload"]
    assert "tool_choice" not in captured["payload"]


def test_openai_compatible_client_sends_standard_tool_messages(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"choices": [{"message": {"content": "done"}}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = OpenAICompatibleModelClient(model="gpt-4o", base_url="https://api.openai.com/v1")
    client.invoke(
        [
            Message(role="assistant", content="", tool_calls=[{"name": "echo", "args": {"value": "hi"}, "id": "call-1"}]),
            Message(role="tool", content="hi", name="echo", tool_call_id="call-1"),
        ],
        tools=[
            {
                "name": "echo",
                "description": "Echo a value.",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
            }
        ],
    )

    assert captured["payload"]["tool_choice"] == "auto"
    assert captured["payload"]["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "Echo a value.",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
            },
        }
    ]
    assert captured["payload"]["messages"] == [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "echo", "arguments": "{\"value\": \"hi\"}"},
                }
            ],
        },
        {"role": "tool", "content": "hi", "tool_call_id": "call-1"},
    ]


def test_openai_compatible_client_preserves_returned_tool_call_id(monkeypatch):
    def fake_urlopen(request, timeout):
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {"name": "echo", "arguments": "{\"value\":\"hi\"}"},
                                }
                            ]
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = OpenAICompatibleModelClient(model="gpt-4o", base_url="https://api.openai.com/v1")
    response = client.invoke([Message(role="user", content="hello")], tools=[{"name": "echo"}])

    assert response.tool_call is not None
    assert response.tool_call.id == "call-1"
    assert response.tool_call.name == "echo"
    assert response.tool_call.arguments == {"value": "hi"}
