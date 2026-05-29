"""Standard LangGraph runtime.

This package is the production-oriented runtime candidate. It uses LangChain /
LangGraph standard message types and can be selected from the CLI for parity
comparison with the reference runtime.
"""

from .graph import build_standard_graph
from .model_adapters import StandardOllamaModelClient
from .nodes import StandardGraphComponents, StandardModelClient
from .runner import StandardLangGraphAgentRuntime
from .state import StandardAgentState, build_initial_state
from .tools import tool_spec_to_structured_tool

__all__ = [
    "StandardLangGraphAgentRuntime",
    "StandardAgentState",
    "StandardGraphComponents",
    "StandardModelClient",
    "StandardOllamaModelClient",
    "build_initial_state",
    "build_standard_graph",
    "tool_spec_to_structured_tool",
]
