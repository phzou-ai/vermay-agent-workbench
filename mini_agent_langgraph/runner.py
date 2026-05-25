from __future__ import annotations

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

from .graph import build_graph
from .nodes import GraphComponents
from .state import AgentState


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

    def __post_init__(self) -> None:
        self.progress = self.progress or ProgressReporter(enabled=False)
        components = GraphComponents(
            model=self.model,
            registry=self.registry,
            context_builder=self.context_builder,
            permission_gate=self.permission_gate,
            tool_executor=self.tool_executor,
            observation_handler=self.observation_handler,
            memory=self.memory,
            trace=self.trace,
        )
        self.graph = build_graph(components)

    def run(self, user_input: str, skills: list[str] | None = None) -> str:
        if skills:
            self.trace.log_event(
                "langgraph_skills_ignored",
                {"skill_count": len(skills), "reason": "Batch 1 does not implement skill injection."},
            )

        self.trace.log_event("langgraph_run_started", {"user_input": user_input})
        self.progress.event(None, "run_started", input=user_input, max_steps=self.max_steps)

        initial_state: AgentState = {
            "user_input": user_input,
            "messages": [],
            "observations": [],
            "tool_call": None,
            "permission_decision": None,
            "tool_result": None,
            "observation": None,
            "final_answer": None,
            "step": 1,
            "max_steps": self.max_steps,
            "errors": [],
        }
        final_state = self.graph.invoke(initial_state)

        final_answer = final_state.get("final_answer")
        if final_answer is not None:
            self.trace.log_event("langgraph_run_finished", {"final_answer": final_answer})
            return final_answer

        message = f"Stopped after max_steps={self.max_steps}"
        self.trace.log_event("langgraph_max_steps_reached", {"message": message})
        return message
