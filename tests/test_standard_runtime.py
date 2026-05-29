from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from mini_agent.standard_runtime.graph import build_standard_graph
from mini_agent.standard_runtime.nodes import StandardGraphComponents
from mini_agent.standard_runtime.routing import latest_ai_message, route_after_model, route_loop_limit
from mini_agent.standard_runtime.state import build_initial_state


class FakeStandardModel:
    def __init__(self, response: AIMessage) -> None:
        self.response = response
        self.calls = []

    def invoke(self, messages, tools):
        self.calls.append((messages, tools))
        return self.response


def test_standard_initial_state_uses_langchain_messages():
    state = build_initial_state("hello", system_prompt="system prompt", max_loops=3)

    assert isinstance(state["messages"][0], SystemMessage)
    assert isinstance(state["messages"][1], HumanMessage)
    assert state["messages"][0].content == "system prompt"
    assert state["messages"][1].content == "hello"
    assert state["loop_index"] == 1
    assert state["max_loops"] == 3
    assert state["final_answer"] is None


def test_standard_routing_detects_ai_message_tool_calls():
    state = build_initial_state("weather")
    state["messages"].append(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "weather_forecast",
                    "args": {"location": "Shanghai"},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        )
    )

    assert latest_ai_message(state["messages"]) is state["messages"][-1]
    assert route_after_model(state) == "tool_calls"


def test_standard_routing_detects_final_answer():
    state = build_initial_state("hello")
    state["messages"].append(AIMessage(content="final answer"))

    assert route_after_model(state) == "final"


def test_standard_loop_limit_uses_loop_index():
    assert route_loop_limit({**build_initial_state("hello", max_loops=2), "loop_index": 2}) == "continue"
    assert route_loop_limit({**build_initial_state("hello", max_loops=2), "loop_index": 3}) == "max_loops"


def test_standard_graph_appends_ai_message_with_add_messages():
    model = FakeStandardModel(AIMessage(content="final answer"))
    graph = build_standard_graph(StandardGraphComponents(model=model, tools=[]))

    output = graph.invoke(build_initial_state("hello", system_prompt="system prompt"))

    assert output["final_answer"] == "final answer"
    assert len(output["messages"]) == 3
    assert isinstance(output["messages"][-1], AIMessage)
    assert model.calls[0][0][0].content == "system prompt"
    assert model.calls[0][0][1].content == "hello"
