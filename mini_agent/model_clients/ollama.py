from __future__ import annotations

import json
import urllib.error
import urllib.request

from mini_agent.types import Message, ModelResponse, ToolCall


class OllamaModelClient:
    """Ollama chat adapter using a small JSON protocol for tool calls."""

    def __init__(
        self,
        model: str = "deepseek-v4-flash:cloud",
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: int = 120,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def invoke(self, messages: list[Message], tools: list[dict]) -> ModelResponse:
        ollama_messages = self._to_ollama_messages(messages, tools)
        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }

        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            return ModelResponse(content=f"Ollama request failed: {exc}")

        try:
            body = json.loads(raw)
            content = body["message"]["content"]
            decision = json.loads(content)
        except (KeyError, json.JSONDecodeError, TypeError) as exc:
            return ModelResponse(content=f"Invalid Ollama response: {exc}; raw={raw[:1000]}")

        return self._parse_decision(decision)

    def _to_ollama_messages(self, messages: list[Message], tools: list[dict]) -> list[dict[str, str]]:
        protocol = {
            "role": "system",
            "content": (
                "Return only JSON. Choose one action.\n"
                "Final answer: {\"action\":\"final\",\"content\":\"...\"}\n"
                "Tool call: {\"action\":\"tool_call\",\"name\":\"tool_name\",\"arguments\":{...}}\n"
                "Only call tools listed below. Dangerous tools may require approval.\n"
                "If a tool observation starts with TOOL_ERROR, either choose a corrected tool call "
                "or return a final answer explaining the failure. Do not repeat the same failing call.\n"
                f"Available tools:\n{json.dumps(tools, ensure_ascii=False, indent=2)}"
            ),
        }

        converted = [protocol]
        for message in messages:
            if message.role == "tool":
                converted.append(
                    {
                        "role": "user",
                        "content": (
                            f"Tool observation from {message.name}:\n{message.content}\n\n"
                            "This tool has already been executed. Return a final answer unless a different "
                            "tool is strictly required."
                        ),
                    }
                )
                continue

            converted.append({"role": message.role, "content": message.content})
        return converted

    def _parse_decision(self, decision: dict) -> ModelResponse:
        action = decision.get("action")
        if decision == {}:
            return ModelResponse(content="Model returned empty JSON instead of an agent action.")

        if action == "tool_call":
            name = decision.get("name")
            arguments = decision.get("arguments", {})
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return ModelResponse(content=f"Invalid tool_call decision: {decision}")
            return ModelResponse(content=f"Calling tool {name}.", tool_call=ToolCall(name=name, arguments=arguments))

        if action == "final":
            content = decision.get("content")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False, indent=2)
            return ModelResponse(content=content)

        if "message" in decision or "status" in decision:
            return ModelResponse(content=json.dumps(decision, ensure_ascii=False))

        return ModelResponse(content=f"Invalid model action: {decision}")

