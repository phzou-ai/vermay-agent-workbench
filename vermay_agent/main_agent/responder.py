from __future__ import annotations

from typing import Protocol

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from vermay_agent.langgraph_runtime.nodes import ModelClient

from .models import MessageRecord, MessageRole


class LocalMessageResponder(Protocol):
    def respond(self, messages: list[MessageRecord]) -> list[dict]: ...


class DirectModelLocalMessageResponder:
    def __init__(self, model: ModelClient) -> None:
        self.model = model

    def respond(self, messages: list[MessageRecord]) -> list[dict]:
        invocation = self.model.invoke(messages=[_to_langchain_message(message) for message in messages], tools=[])
        content = _string_content(invocation.message)
        return [{"kind": "text", "text": content}]


def _to_langchain_message(message: MessageRecord) -> BaseMessage:
    text = _text_from_parts(message.parts)
    if message.role == MessageRole.SYSTEM:
        return SystemMessage(content=text)
    if message.role == MessageRole.AGENT:
        return AIMessage(content=text)
    return HumanMessage(content=text)


def _text_from_parts(parts: list[dict]) -> str:
    return "\n".join(str(part.get("text", "")).strip() for part in parts if isinstance(part.get("text"), str)).strip()


def _string_content(message: AIMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return str(content)
