from __future__ import annotations

import re
from dataclasses import dataclass

from mini_agent.context_builder import ContextBuilder
from mini_agent.memory import MemoryStore
from mini_agent.model_clients import ModelClient
from mini_agent.observation import ObservationHandler
from mini_agent.permission import PermissionGate
from mini_agent.progress import ProgressReporter
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
        components.progress.event(state["step"], "approval_required", tool=tool_name)
        return {"final_answer": message}

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
            exit_code=_tool_exit_code(result.output),
            command_summary=_tool_command_summary(result.output),
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
            summary=_observation_summary(tool_result.output, observation.content),
        )
        return {"observation": observation, "observations": observations}

    return node


def _tool_command_summary(output: object) -> str | None:
    if isinstance(output, dict) and "command" in output:
        command = str(output["command"])
        matches = re.findall(
            r"(?:/snap/bin/microk8s\s+kubectl|microk8s\s+kubectl|kubectl)\s+(?:get|describe)\s+[^;]+",
            command,
        )
        if matches:
            return matches[0].strip()
        return command
    return None


def _tool_exit_code(output: object) -> object:
    if isinstance(output, dict) and "exit_code" in output:
        return output["exit_code"]
    return None


def _observation_summary(output: object, content: str) -> str:
    if isinstance(output, dict):
        stdout = str(output.get("stdout") or "")
        stderr = str(output.get("stderr") or "")
        if stdout:
            lines = stdout.splitlines()
            preview = "\n".join(lines[:8])
            if len(lines) > 8:
                preview += f"\n... ({len(lines) - 8} more lines in JSONL trace)"
            return f"stdout_lines: {len(lines)}\n{preview}"
        if stderr:
            return f"stderr:\n{stderr}"
    return content


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
