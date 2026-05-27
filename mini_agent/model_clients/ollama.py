from __future__ import annotations

import json
import urllib.error
import urllib.request

from mini_agent.env_config import load_prefixed_env
from mini_agent.types import Message, ModelResponse, ToolCall


class OllamaModelClient:
    """Ollama chat adapter using a small JSON protocol for tool calls."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        config = self._load_config()
        self.model = model or config["model"]
        self.base_url = (base_url or config["base_url"]).rstrip("/")
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else config["timeout_seconds"]

    def _load_config(self) -> dict:
        values = load_prefixed_env("MINI_AGENT_OLLAMA_")
        return {
            "model": values.get("MINI_AGENT_OLLAMA_MODEL", "deepseek-v4-flash:cloud"),
            "base_url": values.get("MINI_AGENT_OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            "timeout_seconds": int(values.get("MINI_AGENT_OLLAMA_TIMEOUT_SECONDS", "120")),
        }

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
        except urllib.error.HTTPError as exc:
            return ModelResponse(content=self._format_http_error(exc))
        except urllib.error.URLError as exc:
            return ModelResponse(content=f"Ollama request failed: {exc}")

        try:
            body = json.loads(raw)
            content = body["message"]["content"]
        except (KeyError, json.JSONDecodeError, TypeError) as exc:
            return ModelResponse(content=f"Invalid Ollama response: {exc}; raw={raw[:1000]}")

        return self._parse_content(content)

    def _format_http_error(self, exc: urllib.error.HTTPError) -> str:
        detail = ""
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = ""

        if body:
            try:
                payload = json.loads(body)
                error = payload.get("error")
                if isinstance(error, str):
                    detail = f": {error}"
                else:
                    detail = f": {body[:1000]}"
            except json.JSONDecodeError:
                detail = f": {body[:1000]}"

        return f"Ollama request failed: HTTP {exc.code} {exc.reason}{detail}"

    def _parse_content(self, content: str) -> ModelResponse:
        normalized = content.strip()
        if normalized.startswith("```"):
            lines = normalized.splitlines()
            if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].strip() == "```":
                normalized = "\n".join(lines[1:-1]).strip()

        try:
            decision = json.loads(normalized)
        except json.JSONDecodeError:
            return ModelResponse(content=content)

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

        if "content" in decision:
            content = decision["content"]
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False, indent=2)
            return ModelResponse(content=content)

        if "message" in decision or "status" in decision:
            return ModelResponse(content=json.dumps(decision, ensure_ascii=False))

        return ModelResponse(content=f"Invalid model action: {decision}")
