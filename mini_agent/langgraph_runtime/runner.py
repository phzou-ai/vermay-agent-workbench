from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from mini_agent.context_builder import ContextBuilder
from mini_agent.memory import MemoryStore
from mini_agent.model_clients import ModelClient
from mini_agent.observation import ObservationHandler
from mini_agent.permission import PermissionGate
from mini_agent.progress import ProgressReporter
from mini_agent.tool_executor import ToolExecutor
from mini_agent.tool_registry import ToolRegistry
from mini_agent.trace import TraceLogger
from mini_agent.types import Message, Observation, PermissionDecision, ToolCall, ToolResult

from .graph import build_graph
from .nodes import GraphComponents
from .results import RunResult
from .state import AgentState
from .streaming import DEFAULT_STREAM_MODES, GraphStreamReporter, normalize_stream_chunk, parse_stream_modes


@dataclass
class _InterruptData:
    value: Any
    message: str


@dataclass
class LangGraphAgentRuntime:
    model: ModelClient
    registry: ToolRegistry
    context_builder: ContextBuilder
    permission_gate: PermissionGate
    tool_executor: ToolExecutor
    observation_handler: ObservationHandler
    memory: MemoryStore
    trace: TraceLogger
    max_steps: int = 5
    progress: ProgressReporter | None = None
    stream_reporter: GraphStreamReporter | None = None
    checkpointer: object | None = None
    checkpoint_path: Path | None = None
    _checkpoint_conn: sqlite3.Connection | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.progress = self.progress or ProgressReporter(enabled=False)
        self.stream_reporter = self.stream_reporter or GraphStreamReporter(enabled=False)
        checkpointer = self._build_checkpointer()
        components = GraphComponents(
            model=self.model,
            registry=self.registry,
            context_builder=self.context_builder,
            permission_gate=self.permission_gate,
            tool_executor=self.tool_executor,
            observation_handler=self.observation_handler,
            memory=self.memory,
            trace=self.trace,
            progress=self.progress,
        )
        self.graph = build_graph(components, checkpointer=checkpointer)

    def _build_checkpointer(self):
        serde = JsonPlusSerializer(
            allowed_msgpack_modules=[Message, Observation, PermissionDecision, ToolCall, ToolResult]
        )
        if self.checkpointer is not None:
            return self.checkpointer
        if self.checkpoint_path is None:
            return InMemorySaver(serde=serde)

        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self._checkpoint_conn = sqlite3.connect(str(self.checkpoint_path), check_same_thread=False)
        return SqliteSaver(self._checkpoint_conn, serde=serde)

    def run(
        self,
        user_input: str,
        skills: list[str] | None = None,
        stream_modes: Sequence[str] | None = None,
        thread_id: str | None = None,
    ) -> str:
        return self.start(user_input, skills=skills, stream_modes=stream_modes, thread_id=thread_id).to_output()

    def start(
        self,
        user_input: str,
        skills: list[str] | None = None,
        stream_modes: Sequence[str] | None = None,
        thread_id: str | None = None,
    ) -> RunResult:
        if skills:
            self.trace.log_event(
                "langgraph_skills_ignored",
                {"skill_count": len(skills), "reason": "Skill injection is not implemented in the current runtime."},
            )

        self.trace.log_event("langgraph_run_started", {"user_input": user_input})
        self.progress.event(None, "run_started", input=user_input, max_steps=self.max_steps)

        initial_state = self._initial_state(user_input)
        active_thread_id = thread_id or str(uuid4())
        final_state = self._invoke(initial_state, thread_id=active_thread_id, stream_modes=stream_modes)

        interrupt = self._extract_interrupt(final_state, active_thread_id)
        if interrupt is not None:
            self.trace.log_event(
                "langgraph_run_interrupted",
                {"thread_id": active_thread_id, "interrupt": interrupt.value},
            )
            return RunResult(
                thread_id=active_thread_id,
                interrupt=interrupt.value,
                interrupt_message=interrupt.message,
                state=final_state,
            )

        final_answer = final_state.get("final_answer")
        if final_answer is not None:
            self.trace.log_event("langgraph_run_finished", {"final_answer": final_answer})
            return RunResult(thread_id=active_thread_id, final_answer=final_answer, state=final_state)

        message = f"Stopped after max_steps={self.max_steps}"
        self.trace.log_event("langgraph_max_steps_reached", {"message": message})
        return RunResult(thread_id=active_thread_id, state=final_state, stop_message=message)

    def _initial_state(self, user_input: str) -> AgentState:
        return {
            "user_input": user_input,
            "messages": [],
            "observations": [],
            "tool_call": None,
            "permission_decision": None,
            "approval_result": None,
            "tool_result": None,
            "observation": None,
            "final_answer": None,
            "step": 1,
            "max_steps": self.max_steps,
            "errors": [],
        }

    def _invoke(
        self,
        input_state: AgentState,
        thread_id: str,
        stream_modes: Sequence[str] | None = None,
    ) -> dict:
        if stream_modes is None:
            return self.graph.invoke(input_state, config=self._config(thread_id))

        modes = parse_stream_modes(stream_modes or DEFAULT_STREAM_MODES)
        final_state: dict = {}
        config = self._config(thread_id)
        for raw_chunk in self.graph.stream(input_state, config=config, stream_mode=list(modes)):
            mode, chunk = normalize_stream_chunk(raw_chunk, modes)
            self.stream_reporter.event(mode, chunk)
            if mode == "values" and isinstance(chunk, dict):
                final_state = chunk
            elif mode == "updates" and isinstance(chunk, dict) and "__interrupt__" in chunk:
                final_state = {**final_state, "__interrupt__": chunk["__interrupt__"]}

        if final_state:
            return final_state

        snapshot = self.graph.get_state(config)
        return dict(snapshot.values)

    def resume_approval(self, thread_id: str | None, approved: bool, reason: str | None = None) -> str:
        if not thread_id:
            raise ValueError("thread_id is required to resume an approval interrupt")
        return self.resume(thread_id=thread_id, approved=approved, reason=reason).to_output()

    def resume(
        self,
        thread_id: str,
        approved: bool,
        reason: str | None = None,
    ) -> RunResult:
        if not thread_id:
            raise ValueError("thread_id is required to resume an approval interrupt")

        self.trace.log_event(
            "langgraph_resume_approval_requested",
            {"thread_id": thread_id, "approved": approved, "reason": reason},
        )
        final_state = self.graph.invoke(
            Command(resume={"approved": approved, "reason": reason}),
            config=self._config(thread_id),
        )

        interrupt = self._extract_interrupt(final_state, thread_id)
        if interrupt is not None:
            self.trace.log_event(
                "langgraph_run_interrupted",
                {"thread_id": thread_id, "interrupt": interrupt.value},
            )
            return RunResult(
                thread_id=thread_id,
                interrupt=interrupt.value,
                interrupt_message=interrupt.message,
                state=final_state,
            )

        final_answer = final_state.get("final_answer")
        if final_answer is not None:
            self.trace.log_event("langgraph_run_finished", {"final_answer": final_answer})
            return RunResult(thread_id=thread_id, final_answer=final_answer, state=final_state)

        message = f"Resumed thread {thread_id}, but no final answer was produced."
        self.trace.log_event("langgraph_resume_finished_without_answer", {"message": message})
        return RunResult(thread_id=thread_id, state=final_state, stop_message=message)

    def _config(self, thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}}

    def _extract_interrupt(self, state: dict, thread_id: str) -> _InterruptData | None:
        interrupts = state.get("__interrupt__")
        if not interrupts:
            return None

        interrupt_value = getattr(interrupts[0], "value", interrupts[0])
        message = None
        if isinstance(interrupt_value, dict):
            message = interrupt_value.get("message")
        message = message or "Approval required."
        interrupt_message = (
            f"{message}\n"
            f"thread_id: {thread_id}\n"
            "Resume with: mini-agent --thread-id "
            f"{thread_id} --resume-approval true"
        )
        return _InterruptData(value=interrupt_value, message=interrupt_message)
