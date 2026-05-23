from __future__ import annotations

from collections.abc import Callable
import json

from .context_builder import ContextBuilder
from .memory import MemoryStore
from .model_clients import ModelClient
from .observation import ObservationHandler
from .permission import PermissionGate
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
        progress: Callable[[str], None] | None = None,
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
        self.progress = progress

    def run(self, user_input: str, skills: list[str] | None = None) -> str:
        observations: list[Observation] = []
        skills = skills or []

        self.trace.log_event("run_started", {"user_input": user_input})

        for step in range(1, self.max_steps + 1):
            self._progress(f"step {step}/{self.max_steps}: building context")
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

            self._progress(f"step {step}/{self.max_steps}: calling model")
            response = self.model.invoke(messages=messages, tools=self.registry.schemas())
            self.trace.log_event(
                "model_response",
                {
                    "step": step,
                    "content": response.content,
                    "tool_call": response.tool_call.__dict__ if response.tool_call else None,
                },
            )
            self._progress(
                f"step {step}/{self.max_steps}: model response "
                f"{self._preview(response.content, limit=240)}"
            )

            if not response.has_tool_call:
                self.trace.log_event("run_finished", {"step": step, "final_answer": response.content})
                self._progress(f"step {step}/{self.max_steps}: final answer")
                return response.content

            assert response.tool_call is not None
            tool_call_payload = response.tool_call.__dict__
            self._progress(
                f"step {step}/{self.max_steps}: tool_call "
                f"{json.dumps(tool_call_payload, ensure_ascii=False)}"
            )
            decision = self.permission_gate.check(response.tool_call)
            self.trace.log_event(
                "permission_checked",
                {
                    "step": step,
                    "tool_call": response.tool_call.__dict__,
                    "decision": decision.__dict__,
                },
            )
            self._progress(
                f"step {step}/{self.max_steps}: permission "
                f"allowed={decision.allowed} requires_approval={decision.requires_approval} "
                f"reason={decision.reason}"
            )

            if decision.requires_approval:
                message = f"Approval required for tool '{response.tool_call.name}': {decision.reason}"
                self.trace.log_event("approval_required", {"step": step, "message": message})
                self._progress(f"step {step}/{self.max_steps}: approval required")
                return message

            self._progress(f"step {step}/{self.max_steps}: executing tool {response.tool_call.name}")
            result = self.tool_executor.execute(response.tool_call)
            observation = self.observation_handler.process(result)
            observations.append(observation)
            self._progress(
                f"step {step}/{self.max_steps}: tool_result ok={result.ok} "
                f"exit_code={self._tool_exit_code(result.output)} "
                f"command={self._tool_command(result.output)}"
            )
            self._progress(
                f"step {step}/{self.max_steps}: observation "
                f"{self._preview(observation.content, limit=800)}"
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
        self._progress(message)
        return message

    def _progress(self, message: str) -> None:
        if self.progress is not None:
            self.progress(message)

    def _preview(self, value: object, limit: int) -> str:
        text = str(value).replace("\n", "\\n")
        if len(text) > limit:
            return text[:limit] + "...<truncated>"
        return text

    def _tool_command(self, output: object) -> str | None:
        if isinstance(output, dict) and "command" in output:
            return self._preview(output["command"], limit=500)
        return None

    def _tool_exit_code(self, output: object) -> object:
        if isinstance(output, dict) and "exit_code" in output:
            return output["exit_code"]
        return None
