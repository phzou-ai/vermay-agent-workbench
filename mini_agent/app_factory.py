from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mini_agent.langgraph_runtime import LangGraphAgentRuntime, ModelProviderConfig, build_model_client

from .checkpointing import build_sqlite_checkpointer
from .context_builder import ContextBuilder
from .mcp_client import MCPToolLoader
from .memory import SQLiteMemoryStore
from .permission import PermissionGate
from .progress import ProgressReporter
from .runtime_context import RuntimeContextProvider
from .skills import SkillStore
from .storage import AgentStore
from .tool_registry import ToolRegistry
from .tools.devops import register_devops_tools
from .tools.weather import register_weather_tools
from .trace import TraceLogger


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRACE_PATH = ROOT / "traces" / "latest.jsonl"
DEFAULT_CHECKPOINT_PATH = ROOT / "data" / "checkpoints" / "langgraph.sqlite"
DEFAULT_AGENT_STORE_PATH = ROOT / "data" / "agent.sqlite"
DEFAULT_SKILLS_PATH = ROOT / "skills"
DEFAULT_SKILL_PROPOSALS_PATH = ROOT / "data" / "skill_proposals"
DEFAULT_MCP_CONFIG_PATH = ROOT / "config" / "mcp_servers.json"


@dataclass(frozen=True)
class RuntimeFactoryConfig:
    model: ModelProviderConfig = field(default_factory=ModelProviderConfig)
    max_loops: int = 5
    show_progress: bool = True
    trace_path: Path = DEFAULT_TRACE_PATH
    checkpoint_path: Path = DEFAULT_CHECKPOINT_PATH
    agent_store_path: Path = DEFAULT_AGENT_STORE_PATH
    skills_path: Path = DEFAULT_SKILLS_PATH
    skill_proposals_path: Path = DEFAULT_SKILL_PROPOSALS_PATH
    mcp_config_path: Path = DEFAULT_MCP_CONFIG_PATH


def build_runtime(config: RuntimeFactoryConfig | None = None) -> LangGraphAgentRuntime:
    active_config = config or RuntimeFactoryConfig()
    registry = ToolRegistry()
    register_devops_tools(registry)
    register_weather_tools(registry)
    for tool in MCPToolLoader(active_config.mcp_config_path).load_tools():
        registry.register(tool)
    checkpointer = build_sqlite_checkpointer(active_config.checkpoint_path)
    agent_store = AgentStore(active_config.agent_store_path)
    memory_store = SQLiteMemoryStore(agent_store)
    skill_store = SkillStore(
        authored_dir=active_config.skills_path,
        proposals_dir=active_config.skill_proposals_path,
        store=agent_store,
    )

    return LangGraphAgentRuntime(
        model=build_model_client(active_config.model),
        tools=registry.tools(),
        permission_gate=PermissionGate(registry),
        system_prompt=_default_system_prompt(),
        trace=TraceLogger(active_config.trace_path),
        max_loops=active_config.max_loops,
        checkpointer=checkpointer,
        progress=ProgressReporter(enabled=active_config.show_progress),
        context_provider=RuntimeContextProvider(memory=memory_store, skills=skill_store),
        close_callbacks=[checkpointer.conn.close, agent_store.close],
    )


def _default_system_prompt() -> str:
    return ContextBuilder().build(user_input="", memory=[], skills=[], observations=[])[0].content
