from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool

from mini_agent.model_clients import OllamaModelClient, OpenAICompatibleModelClient
from mini_agent.tool_schema import tool_schemas_from_tools
from mini_agent.types import Message


@dataclass(frozen=True)
class ModelInvocation:
    """Thin project wrapper around the model's standard LangChain message."""

    message: AIMessage


class OllamaModelAdapter:
    """Adapter from the project Ollama client to LangChain standard messages."""

    def __init__(self, client: OllamaModelClient) -> None:
        self.client = client

    def invoke(self, messages: list[BaseMessage], tools: list[BaseTool]) -> ModelInvocation:
        response = self.client.invoke(
            messages=[_to_project_message(message) for message in messages],
            tools=tool_schemas_from_tools(tools),
        )
        if response.tool_call is None:
            return ModelInvocation(message=AIMessage(content=response.content))

        return ModelInvocation(
            message=AIMessage(
                content=response.content,
                tool_calls=[
                    {
                        "name": response.tool_call.name,
                        "args": response.tool_call.arguments,
                        "id": f"call-{uuid4().hex}",
                        "type": "tool_call",
                    }
                ],
            )
        )


class OpenAICompatibleModelAdapter:
    """Adapter from an OpenAI-compatible client to LangChain standard messages."""

    def __init__(self, client: OpenAICompatibleModelClient) -> None:
        self.client = client

    def invoke(self, messages: list[BaseMessage], tools: list[BaseTool]) -> ModelInvocation:
        response = self.client.invoke(
            messages=[_to_project_message(message) for message in messages],
            tools=tool_schemas_from_tools(tools),
        )
        if response.tool_call is None:
            return ModelInvocation(message=AIMessage(content=response.content))

        return ModelInvocation(
            message=AIMessage(
                content=response.content,
                tool_calls=[
                    {
                        "name": response.tool_call.name,
                        "args": response.tool_call.arguments,
                        "id": f"call-{uuid4().hex}",
                        "type": "tool_call",
                    }
                ],
            )
        )


class RuleRouterModelAdapter:
    """Deterministic rule-based router across model adapters."""

    def __init__(self, *, profiles: dict[str, object], rules: list[dict], default_profile: str) -> None:
        self.profiles = profiles
        self.rules = rules
        self.default_profile = default_profile
        if default_profile not in profiles:
            raise ValueError(f"router default profile is not defined: {default_profile}")

    def invoke(self, messages: list[BaseMessage], tools: list[BaseTool]) -> ModelInvocation:
        profile_name = self._select_profile(messages)
        profile = self.profiles[profile_name]
        return profile.invoke(messages, tools)

    def _select_profile(self, messages: list[BaseMessage]) -> str:
        latest_text = _latest_human_text(messages).lower()
        has_tool_error = any(
            getattr(message, "type", "") == "tool"
            and any(marker in str(message.content).lower() for marker in ("error", "failed", "exception"))
            for message in messages
        )
        for rule in self.rules:
            profile = rule.get("profile")
            if not isinstance(profile, str) or profile not in self.profiles:
                continue
            contains = rule.get("contains")
            if isinstance(contains, list) and any(str(item).lower() in latest_text for item in contains):
                return profile
            min_messages = rule.get("min_messages")
            if isinstance(min_messages, int) and len(messages) >= min_messages:
                return profile
            if rule.get("on_tool_error") is True and has_tool_error:
                return profile
        return self.default_profile


def _to_project_message(message: BaseMessage) -> Message:
    message_type = getattr(message, "type", "")
    content = str(message.content)
    if message_type == "human":
        return Message(role="user", content=content)
    if message_type == "ai":
        return Message(role="assistant", content=content)
    if message_type == "tool":
        return Message(role="tool", content=content, name=getattr(message, "name", None))
    if message_type == "system":
        return Message(role="system", content=content)
    return Message(role="user", content=content)


def _latest_human_text(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if getattr(message, "type", "") == "human":
            return str(message.content)
    return ""
