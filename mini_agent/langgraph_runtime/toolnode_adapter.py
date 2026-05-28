from __future__ import annotations

from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import StructuredTool

from mini_agent.types import ToolCall, ToolSpec


def tool_spec_to_structured_tool(spec: ToolSpec) -> StructuredTool:
    return StructuredTool.from_function(
        func=spec.func,
        name=spec.name,
        description=spec.description,
    )


def tool_call_to_ai_message(tool_call: ToolCall, call_id: str | None = None) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": tool_call.name,
                "args": tool_call.arguments,
                "id": call_id or f"call-{uuid4()}",
                "type": "tool_call",
            }
        ],
    )


def extract_tool_messages(messages: list[BaseMessage]) -> list[ToolMessage]:
    return [message for message in messages if isinstance(message, ToolMessage)]
