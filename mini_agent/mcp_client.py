from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from langchain_core.tools import StructuredTool

from .tool_schema import DANGEROUS_METADATA_KEY


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    transport: str
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    read_only: bool = False
    read_only_tools: set[str] = field(default_factory=set)
    tool_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class MCPToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    server: MCPServerConfig


class MCPToolLoader:
    def __init__(
        self,
        config_path: Path,
        *,
        discovery: Callable[[MCPServerConfig], list[MCPToolDefinition]] | None = None,
        caller: Callable[[MCPServerConfig, str, dict[str, Any]], Any] | None = None,
    ) -> None:
        self.config_path = config_path
        self.discovery = discovery
        self.caller = caller

    def load_tools(self) -> list[StructuredTool]:
        tools = []
        for server in load_mcp_server_configs(self.config_path):
            definitions = self._discover(server)
            for definition in definitions:
                tools.append(self._to_structured_tool(definition))
        return tools

    def _discover(self, server: MCPServerConfig) -> list[MCPToolDefinition]:
        if self.discovery is not None:
            return self.discovery(server)
        return asyncio.run(_discover_stdio_tools(server))

    def _to_structured_tool(self, definition: MCPToolDefinition) -> StructuredTool:
        tool_name = f"mcp_{_safe_name(definition.server.name)}_{_safe_name(definition.name)}"
        dangerous = not _is_read_only(definition.server, definition.name)

        def call_tool(**kwargs):
            if self.caller is not None:
                return self.caller(definition.server, definition.name, kwargs)
            return asyncio.run(_call_stdio_tool(definition.server, definition.name, kwargs))

        return StructuredTool(
            name=tool_name,
            description=definition.description or f"MCP tool {definition.name} from {definition.server.name}",
            args_schema=definition.input_schema or {"type": "object", "properties": {}},
            func=call_tool,
            metadata={
                DANGEROUS_METADATA_KEY: dangerous,
                "mcp_server": definition.server.name,
                "mcp_tool": definition.name,
            },
        )


def load_mcp_server_configs(path: Path) -> list[MCPServerConfig]:
    if not path.exists():
        return []
    body = json.loads(path.read_text(encoding="utf-8"))
    servers = body.get("servers") or {}
    if not isinstance(servers, dict):
        raise ValueError("MCP config 'servers' must be an object")
    configs = []
    for name, raw in servers.items():
        if not isinstance(raw, dict):
            raise ValueError(f"MCP server '{name}' must be an object")
        transport = str(raw.get("transport") or "stdio")
        if transport != "stdio":
            raise ValueError(f"MCP server '{name}' transport is unsupported: {transport}")
        args = raw.get("args") or []
        env = raw.get("env") or {}
        read_only_tools = raw.get("read_only_tools") or []
        tool_overrides = raw.get("tools") or {}
        configs.append(
            MCPServerConfig(
                name=str(name),
                transport=transport,
                command=raw.get("command"),
                args=[str(item) for item in args],
                env={str(key): str(value) for key, value in env.items()} if isinstance(env, dict) else {},
                read_only=bool(raw.get("read_only", False)),
                read_only_tools={str(item) for item in read_only_tools},
                tool_overrides=tool_overrides if isinstance(tool_overrides, dict) else {},
            )
        )
    return configs


async def _discover_stdio_tools(server: MCPServerConfig) -> list[MCPToolDefinition]:
    if not server.command:
        raise ValueError(f"MCP server '{server.name}' requires command")
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        raise RuntimeError("MCP SDK is not installed. Install the 'mcp' Python package.") from exc

    params = StdioServerParameters(command=server.command, args=server.args, env=server.env or None)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            definitions = []
            for tool in result.tools:
                definitions.append(
                    MCPToolDefinition(
                        name=tool.name,
                        description=tool.description or "",
                        input_schema=tool.inputSchema or {"type": "object", "properties": {}},
                        server=server,
                    )
                )
            return definitions


async def _call_stdio_tool(server: MCPServerConfig, tool_name: str, arguments: dict[str, Any]) -> Any:
    if not server.command:
        raise ValueError(f"MCP server '{server.name}' requires command")
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        raise RuntimeError("MCP SDK is not installed. Install the 'mcp' Python package.") from exc

    params = StdioServerParameters(command=server.command, args=server.args, env=server.env or None)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return _serialize_mcp_result(result)


def _serialize_mcp_result(result: Any) -> Any:
    content = getattr(result, "content", None)
    if isinstance(content, list):
        serialized = []
        for item in content:
            text = getattr(item, "text", None)
            if text is not None:
                serialized.append(str(text))
            else:
                serialized.append(str(item))
        return "\n".join(serialized)
    return str(result)


def _is_read_only(server: MCPServerConfig, tool_name: str) -> bool:
    override = server.tool_overrides.get(tool_name)
    if isinstance(override, dict) and override.get("read_only") is True:
        return True
    return server.read_only or tool_name in server.read_only_tools


def _safe_name(value: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()
    return name or "tool"
