from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .json_decision import parse_json_decision
from vermay_agent.types import Message, ModelResponse, ToolCall


class OpenAICompatibleModelClient:
    """OpenAI chat-completions compatible HTTP client."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str | None = None,
        api_key_env: str | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or (os.environ.get(api_key_env) if api_key_env else None)
        self.timeout_seconds = timeout_seconds

    def invoke(self, messages: list[Message], tools: list[dict]) -> ModelResponse:
        payload = {
            "model": self.model,
            "messages": [_to_openai_message(message) for message in messages],
            "temperature": 0,
        }
        if tools:
            payload["tools"] = [_to_openai_tool(tool) for tool in tools]
            payload["tool_choice"] = "auto"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return ModelResponse(content=self._format_http_error(exc))
        except urllib.error.URLError as exc:
            return ModelResponse(content=f"OpenAI-compatible request failed: {exc}")

        try:
            body = json.loads(raw)
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
            return ModelResponse(content=f"Invalid OpenAI-compatible response: {exc}; raw={raw[:1000]}")

        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            tool_call_id = tool_calls[0].get("id")
            function = tool_calls[0].get("function") or {}
            name = function.get("name")
            raw_arguments = function.get("arguments") or "{}"
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else dict(raw_arguments)
            except (TypeError, json.JSONDecodeError):
                arguments = {}
            if isinstance(name, str):
                return ModelResponse(
                    content=f"Calling tool {name}.",
                    tool_call=ToolCall(
                        name=name,
                        arguments=arguments,
                        id=tool_call_id if isinstance(tool_call_id, str) else None,
                    ),
                )

        content = message.get("content") or ""
        parsed = _parse_json_action(content)
        if parsed is not None:
            return parsed
        return ModelResponse(content=str(content))

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _format_http_error(self, exc: urllib.error.HTTPError) -> str:
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = ""
        detail = f": {body[:1000]}" if body else ""
        return f"OpenAI-compatible request failed: HTTP {exc.code} {exc.reason}{detail}"


def _to_openai_message(message: Message) -> dict:
    if message.role == "tool":
        payload = {
            "role": "tool",
            "content": message.content,
            "tool_call_id": message.tool_call_id or message.name or "unknown_tool_call",
        }
        return payload

    payload: dict = {"role": message.role, "content": message.content}
    if message.role == "assistant" and message.tool_calls:
        payload["tool_calls"] = [_to_openai_tool_call(tool_call) for tool_call in message.tool_calls]
        if payload["content"] == "":
            payload["content"] = None
    return payload


def _to_openai_tool_call(tool_call: dict) -> dict:
    arguments = tool_call.get("args") or tool_call.get("arguments") or {}
    if not isinstance(arguments, str):
        arguments = json.dumps(arguments, ensure_ascii=False)
    return {
        "id": str(tool_call.get("id") or "unknown_tool_call"),
        "type": "function",
        "function": {
            "name": str(tool_call.get("name") or ""),
            "arguments": arguments,
        },
    }


def _to_openai_tool(tool: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description") or "",
            "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
        },
    }


def _parse_json_action(content: str) -> ModelResponse | None:
    decision = parse_json_decision(content)
    if decision is None:
        return None
    if decision.get("action") == "tool_call":
        name = decision.get("name")
        arguments = decision.get("arguments", {})
        if isinstance(name, str) and isinstance(arguments, dict):
            return ModelResponse(content=f"Calling tool {name}.", tool_call=ToolCall(name=name, arguments=arguments))
    if decision.get("action") == "final" or "content" in decision:
        content_value = decision.get("content", "")
        if not isinstance(content_value, str):
            content_value = json.dumps(content_value, ensure_ascii=False, indent=2)
        return ModelResponse(content=content_value)
    return None
