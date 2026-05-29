from __future__ import annotations

from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage

from mini_agent.model_clients import OllamaModelClient
from mini_agent.types import Message


class StandardOllamaModelClient:
    """Adapter from the project Ollama client to LangChain standard messages."""

    def __init__(
        self,
        client: OllamaModelClient,
        tool_schemas: list[dict],
    ) -> None:
        self.client = client
        self.tool_schemas = tool_schemas

    def invoke(self, messages: list[BaseMessage], tools: list) -> AIMessage:
        response = self.client.invoke(
            messages=[_to_project_message(message) for message in messages],
            tools=self.tool_schemas,
        )
        if response.tool_call is None:
            return AIMessage(content=response.content)

        return AIMessage(
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
