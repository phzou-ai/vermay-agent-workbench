from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mini_agent.langgraph_runtime import LangGraphAgentRuntime, ModelProviderConfig, build_model_client

from .checkpointing import build_sqlite_checkpointer
from .context_builder import ContextBuilder
from .permission import PermissionGate
from .progress import ProgressReporter
from .tool_registry import ToolRegistry
from .tools.devops import register_devops_tools
from .tools.weather import register_weather_tools
from .trace import TraceLogger


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRACE_PATH = ROOT / "traces" / "latest.jsonl"
DEFAULT_CHECKPOINT_PATH = ROOT / "data" / "checkpoints" / "langgraph.sqlite"


@dataclass(frozen=True)
class RuntimeFactoryConfig:
    model: ModelProviderConfig = field(default_factory=ModelProviderConfig)
    max_loops: int = 5
    show_progress: bool = True
    trace_path: Path = DEFAULT_TRACE_PATH
    checkpoint_path: Path = DEFAULT_CHECKPOINT_PATH


def build_runtime(config: RuntimeFactoryConfig | None = None) -> LangGraphAgentRuntime:
    active_config = config or RuntimeFactoryConfig()
    registry = ToolRegistry()
    register_devops_tools(registry)
    register_weather_tools(registry)
    checkpointer = build_sqlite_checkpointer(active_config.checkpoint_path)

    return LangGraphAgentRuntime(
        model=build_model_client(active_config.model),
        tools=registry.tools(),
        permission_gate=PermissionGate(registry),
        system_prompt=_default_system_prompt(),
        trace=TraceLogger(active_config.trace_path),
        max_loops=active_config.max_loops,
        checkpointer=checkpointer,
        progress=ProgressReporter(enabled=active_config.show_progress),
        close_callbacks=[checkpointer.conn.close],
    )


def _default_system_prompt() -> str:
    return ContextBuilder().build(user_input="", memory=[], skills=[], observations=[])[0].content
