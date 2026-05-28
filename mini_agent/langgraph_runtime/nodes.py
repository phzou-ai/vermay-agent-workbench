from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from mini_agent.context_builder import ContextBuilder
from mini_agent.memory import MemoryStore
from mini_agent.model_clients import ModelClient
from mini_agent.observation import ObservationHandler
from mini_agent.permission import PermissionGate
from mini_agent.progress import ProgressReporter
from mini_agent.result_summary import observation_summary, tool_command_summary, tool_exit_code
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
    progress: ProgressReporter


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
        components.progress.event(
            step,
            "context_built",
            messages=len(messages),
            observations=len(state["observations"]),
            message_preview=[
                {"role": message.role, "name": message.name, "content": message.content}
                for message in messages
            ],
        )
        _emit_stream_event(
            "context_built",
            step=step,
            messages=len(messages),
            observations=len(state["observations"]),
        )
        return {"messages": messages}

    return node


def call_model_node(components: GraphComponents):
    def node(state: AgentState) -> dict:
        step = state["step"]
        components.progress.event(step, "model_call_start")
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
        components.progress.event(
            step,
            "model_response",
            content=response.content,
            tool=tool_call.name if tool_call else None,
        )
        _emit_stream_event(
            "model_response",
            step=step,
            has_tool_call=tool_call is not None,
            tool=tool_call.name if tool_call else None,
        )
        if tool_call is None:
            components.progress.event(step, "final_answer")
            return {"final_answer": response.content, "tool_call": None}
        components.progress.event(step, "tool_call", payload=tool_call_payload(tool_call))
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
        components.progress.event(
            state["step"],
            "permission",
            allowed=decision.allowed,
            approval=decision.requires_approval,
            reason=decision.reason,
        )
        _emit_stream_event(
            "permission_checked",
            step=state["step"],
            allowed=decision.allowed,
            requires_approval=decision.requires_approval,
            reason=decision.reason,
        )
        return {"permission_decision": decision}

    return node


def reject_tool_node(components: GraphComponents):
    def node(state: AgentState) -> dict:
        approval = state.get("approval_result") or {}
        if approval.get("approved") is False:
            reason = approval.get("reason") or "approval rejected"
            message = f"Tool call rejected by approval: {reason}"
            components.trace.log_event("langgraph_tool_rejected", {"step": state["step"], "message": message})
            _emit_stream_event("tool_rejected", step=state["step"], message=message)
            return {"final_answer": message}

        decision = state["permission_decision"]
        message = "Tool call rejected."
        if decision is not None:
            message = f"Tool call rejected: {decision.reason}"
        components.trace.log_event("langgraph_tool_rejected", {"step": state["step"], "message": message})
        _emit_stream_event("tool_rejected", step=state["step"], message=message)
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
        resume = interrupt(
            {
                "kind": "approval_required",
                "step": state["step"],
                "tool_call": tool_call_payload(tool_call),
                "permission": permission_payload(decision),
                "message": message,
            }
        )
        _emit_stream_event("approval_resumed_from_interrupt", step=state["step"], tool=tool_name)
        if isinstance(resume, dict):
            approved = bool(resume.get("approved"))
            reason = str(resume.get("reason") or ("approved" if approved else "approval rejected"))
        else:
            approved = bool(resume)
            reason = "approved" if approved else "approval rejected"

        result = {"approved": approved, "reason": reason}
        components.trace.log_event(
            "langgraph_approval_resumed",
            {"step": state["step"], "tool_call": tool_call_payload(tool_call), "approval": result},
        )
        _emit_stream_event("approval_resumed", step=state["step"], approved=approved, reason=reason)
        return {"approval_result": result}

    return node


def execute_tool_node(components: GraphComponents):
    def node(state: AgentState) -> dict:
        tool_call = state["tool_call"]
        if tool_call is None:
            return {"errors": state["errors"] + [{"step": state["step"], "error": "missing tool_call"}]}

        components.progress.event(state["step"], "tool_execute_start", tool=tool_call.name)
        result = components.tool_executor.execute(tool_call)
        components.trace.log_event(
            "langgraph_tool_result",
            {
                "step": state["step"],
                "tool_call": tool_call_payload(tool_call),
                "result": tool_result_payload(result),
            },
        )
        components.progress.event(
            state["step"],
            "tool_result",
            tool=result.name,
            ok=result.ok,
            exit_code=tool_exit_code(result.output),
            command_summary=tool_command_summary(result.output),
        )
        _emit_stream_event(
            "tool_result",
            step=state["step"],
            tool=result.name,
            ok=result.ok,
            exit_code=tool_exit_code(result.output),
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
        components.progress.event(
            state["step"],
            "observation",
            tool=observation.tool_name,
            ok=observation.ok,
            summary=observation_summary(tool_result.output, observation.content),
        )
        _emit_stream_event(
            "observation",
            step=state["step"],
            tool=observation.tool_name,
            ok=observation.ok,
            observations=len(observations),
        )
        return {"observation": observation, "observations": observations}

    return node

def increment_step_node(_: GraphComponents):
    def node(state: AgentState) -> dict:
        _emit_stream_event("step_incremented", step=state["step"], next_step=state["step"] + 1)
        return {
            "step": state["step"] + 1,
            "tool_call": None,
            "permission_decision": None,
            "approval_result": None,
            "tool_result": None,
            "observation": None,
        }

    return node


def _emit_stream_event(event: str, **fields: Any) -> None:
    try:
        writer = get_stream_writer()
    except Exception:
        return
    writer({"event": event, **fields})
