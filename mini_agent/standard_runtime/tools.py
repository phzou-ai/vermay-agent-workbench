from __future__ import annotations

from langchain_core.tools import StructuredTool

from mini_agent.types import ToolSpec


def tool_spec_to_structured_tool(spec: ToolSpec) -> StructuredTool:
    return StructuredTool.from_function(
        func=spec.func,
        name=spec.name,
        description=spec.description,
    )
