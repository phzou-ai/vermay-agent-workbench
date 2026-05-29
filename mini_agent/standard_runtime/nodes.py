from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool

from .state import StandardAgentState


class StandardModelClient(Protocol):
    def invoke(self, messages: list[BaseMessage], tools: list[BaseTool]) -> AIMessage: ...


@dataclass
class StandardGraphComponents:
    model: StandardModelClient
    tools: list[BaseTool]


def call_model_node(components: StandardGraphComponents):
    def node(state: StandardAgentState) -> dict:
        response = components.model.invoke(messages=state["messages"], tools=components.tools)
        updates: dict = {"messages": [response]}
        if not response.tool_calls:
            updates["final_answer"] = str(response.content)
        return updates

    return node
