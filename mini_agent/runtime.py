from __future__ import annotations

import re

from .context_builder import ContextBuilder
from .memory import MemoryStore
from .model_clients import ModelClient
from .observation import ObservationHandler
from .permission import PermissionGate
from .progress import ProgressReporter
from .tool_executor import ToolExecutor
from .tool_registry import ToolRegistry
from .trace import TraceLogger
from .types import Observation


class MiniAgentRuntime:
    def __init__(
        self,
        model: ModelClient,
        registry: ToolRegistry,
        context_builder: ContextBuilder,
        permission_gate: PermissionGate,
        tool_executor: ToolExecutor,
        observation_handler: ObservationHandler,
        memory: MemoryStore,
        trace: TraceLogger,
        max_steps: int = 5,
        progress: ProgressReporter | None = None,
    ) -> None:
        self.model = model
        self.registry = registry
        self.context_builder = context_builder
        self.permission_gate = permission_gate
        self.tool_executor = tool_executor
        self.observation_handler = observation_handler
        self.memory = memory
        self.trace = trace
        self.max_steps = max_steps
        self.progress = progress or ProgressReporter(enabled=False)

    def run(self, user_input: str, skills: list[str] | None = None) -> str:
        observations: list[Observation] = []
        skills = skills or []

        self.trace.log_event("run_started", {"user_input": user_input})
        self.progress.event(None, "run_started", input=user_input, max_steps=self.max_steps)

        for step in range(1, self.max_steps + 1):
            self.progress.event(step, "context_build_start")
            messages = self.context_builder.build(
                user_input=user_input,
                memory=self.memory.load(),
                skills=skills,
                observations=observations,
            )
            self.trace.log_event(
                "context_built",
                {"step": step, "message_count": len(messages), "observation_count": len(observations)},
            )
            self.progress.event(
                step,
                "context_built",
                messages=len(messages),
                observations=len(observations),
                message_preview=[
                    {"role": message.role, "name": message.name, "content": message.content}
                    for message in messages
                ],
            )

            self.progress.event(step, "model_call_start")
            response = self.model.invoke(messages=messages, tools=self.registry.schemas())
            self.trace.log_event(
                "model_response",
                {
                    "step": step,
                    "content": response.content,
                    "tool_call": response.tool_call.__dict__ if response.tool_call else None,
                },
            )
            self.progress.event(
                step,
                "model_response",
                content=response.content,
                tool=response.tool_call.name if response.tool_call else None,
            )

            if not response.has_tool_call:
                self.trace.log_event("run_finished", {"step": step, "final_answer": response.content})
                self.progress.event(step, "final_answer")
                return response.content

            assert response.tool_call is not None
            tool_call_payload = response.tool_call.__dict__
            self.progress.event(step, "tool_call", payload=tool_call_payload)
            decision = self.permission_gate.check(response.tool_call)
            self.trace.log_event(
                "permission_checked",
                {
                    "step": step,
                    "tool_call": response.tool_call.__dict__,
                    "decision": decision.__dict__,
                },
            )
            self.progress.event(
                step,
                "permission",
                allowed=decision.allowed,
                approval=decision.requires_approval,
                reason=decision.reason,
            )

            if decision.requires_approval:
                message = f"Approval required for tool '{response.tool_call.name}': {decision.reason}"
                self.trace.log_event("approval_required", {"step": step, "message": message})
                self.progress.event(step, "approval_required", tool=response.tool_call.name)
                return message

            self.progress.event(step, "tool_execute_start", tool=response.tool_call.name)
            result = self.tool_executor.execute(response.tool_call)
            observation = self.observation_handler.process(result)
            observations.append(observation)
            self.progress.event(
                step,
                "tool_result",
                tool=result.name,
                ok=result.ok,
                exit_code=self._tool_exit_code(result.output),
                command_summary=self._tool_command_summary(result.output),
            )
            self.progress.event(
                step,
                "observation",
                tool=observation.tool_name,
                ok=observation.ok,
                summary=self._observation_summary(result.output, observation.content),
            )
            self.trace.log_event(
                "tool_result",
                {
                    "step": step,
                    "tool_call": response.tool_call.__dict__,
                    "result": result.__dict__,
                    "observation": observation.__dict__,
                },
            )

        message = f"Stopped after max_steps={self.max_steps}"
        self.trace.log_event("max_steps_reached", {"message": message})
        self.progress.event(None, "max_steps_reached", max_steps=self.max_steps)
        return message

    def _tool_command_summary(self, output: object) -> str | None:
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

    def _tool_exit_code(self, output: object) -> object:
        if isinstance(output, dict) and "exit_code" in output:
            return output["exit_code"]
        return None

    def _observation_summary(self, output: object, content: str) -> str:
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
