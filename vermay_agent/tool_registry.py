from __future__ import annotations

from langchain_core.tools import BaseTool

from .tool_schema import DANGEROUS_METADATA_KEY, tool_schemas_from_tools


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"unknown tool: {name}") from exc

    def schemas(self) -> list[dict]:
        return tool_schemas_from_tools(self.tools())

    def names(self) -> list[str]:
        return sorted(self._tools)

    def tools(self) -> list[BaseTool]:
        return [self._tools[name] for name in self.names()]

    def is_dangerous(self, name: str) -> bool:
        tool = self.get(name)
        return bool((tool.metadata or {}).get(DANGEROUS_METADATA_KEY, False))
