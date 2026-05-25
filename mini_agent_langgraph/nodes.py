from __future__ import annotations

from dataclasses import dataclass

from mini_agent.context_builder import ContextBuilder
from mini_agent.memory import MemoryStore
from mini_agent.model_clients import ModelClient
from mini_agent.observation import ObservationHandler
from mini_agent.permission import PermissionGate
from mini_agent.tool_executor import ToolExecutor
from mini_agent.tool_registry import ToolRegistry
from mini_agent.trace import TraceLogger

from .adapters import observation_payload, permission_payload, tool_call_payload, tool_result_payload
from .state import AgentState


@dataclass
class GraphComponents:
    model: ModelClient
    registry: ToolRegistry
    context_builder: ContextBuilder
    permission_gate: PermissionGate
    tool_executor: ToolExecutor
    observation_handler: ObservationHandler
    memory: MemoryStore
    trace: TraceLogger


def build_context_node(components: GraphComponents):
    def node(state: AgentState) -> dict:
        step = state["step"]
        messages = components.context_builder.build(
            user_input=state["user_input"],
            memory=components.memory.load(),
            skills=[],
            observations=state["observations"],
        )
        components.trace.log_event(
            "langgraph_context_built",
            {
                "step": step,
                "message_count": len(messages),
                "observation_count": len(state["observations"]),
            },
        )
        return {"messages": messages}

    return node


def call_model_node(components: GraphComponents):
    def node(state: AgentState) -> dict:
        step = state["step"]
        response = components.model.invoke(messages=state["messages"], tools=components.registry.schemas())
        tool_call = response.tool_call
        components.trace.log_event(
            "langgraph_model_response",
            {
                "step": step,
                "content": response.content,
                "tool_call": tool_call_payload(tool_call),
            },
        )
        if tool_call is None:
            return {"final_answer": response.content, "tool_call": None}
        return {"tool_call": tool_call, "final_answer": None}

    return node


def check_permission_node(components: GraphComponents):
    def node(state: AgentState) -> dict:
        tool_call = state["tool_call"]
        if tool_call is None:
            return {"errors": state["errors"] + [{"step": state["step"], "error": "missing tool_call"}]}

        decision = components.permission_gate.check(tool_call)
        components.trace.log_event(
            "langgraph_permission_checked",
            {
                "step": state["step"],
                "tool_call": tool_call_payload(tool_call),
                "decision": permission_payload(decision),
            },
        )
        return {"permission_decision": decision}

    return node


def reject_tool_node(components: GraphComponents):
    def node(state: AgentState) -> dict:
        decision = state["permission_decision"]
        message = "Tool call rejected."
        if decision is not None:
            message = f"Tool call rejected: {decision.reason}"
        components.trace.log_event("langgraph_tool_rejected", {"step": state["step"], "message": message})
        return {"final_answer": message}

    return node


def approval_required_node(components: GraphComponents):
    def node(state: AgentState) -> dict:
        tool_call = state["tool_call"]
        decision = state["permission_decision"]
        reason = decision.reason if decision else "approval required"
        tool_name = tool_call.name if tool_call else "unknown"
        message = f"Approval required for tool '{tool_name}': {reason}"
        components.trace.log_event(
            "langgraph_approval_required",
            {"step": state["step"], "tool_call": tool_call_payload(tool_call), "message": message},
        )
        return {"final_answer": message}

    return node


def execute_tool_node(components: GraphComponents):
    def node(state: AgentState) -> dict:
        tool_call = state["tool_call"]
        if tool_call is None:
            return {"errors": state["errors"] + [{"step": state["step"], "error": "missing tool_call"}]}

        result = components.tool_executor.execute(tool_call)
        components.trace.log_event(
            "langgraph_tool_result",
            {
                "step": state["step"],
                "tool_call": tool_call_payload(tool_call),
                "result": tool_result_payload(result),
            },
        )
        return {"tool_result": result}

    return node


def handle_observation_node(components: GraphComponents):
    def node(state: AgentState) -> dict:
        tool_result = state["tool_result"]
        if tool_result is None:
            return {"errors": state["errors"] + [{"step": state["step"], "error": "missing tool_result"}]}

        observation = components.observation_handler.process(tool_result)
        observations = state["observations"] + [observation]
        components.trace.log_event(
            "langgraph_observation",
            {
                "step": state["step"],
                "observation": observation_payload(observation),
            },
        )
        return {"observation": observation, "observations": observations}

    return node


def increment_step_node(_: GraphComponents):
    def node(state: AgentState) -> dict:
        return {
            "step": state["step"] + 1,
            "tool_call": None,
            "permission_decision": None,
            "tool_result": None,
            "observation": None,
        }

    return node
