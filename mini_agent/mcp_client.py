from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from langchain_core.tools import StructuredTool

from .tool_schema import DANGEROUS_METADATA_KEY


TOOL_EXPOSURE_POLICIES = {"none", "read_only", "allowlist", "all"}


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
    tool_exposure: str = "read_only"


@dataclass(frozen=True)
class MCPToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    server: MCPServerConfig


@dataclass(frozen=True)
class MCPResourceDefinition:
    server: MCPServerConfig
    uri: str
    name: str
    title: str | None = None
    description: str = ""
    mime_type: str | None = None
    size: int | None = None


@dataclass(frozen=True)
class MCPPromptDefinition:
    server: MCPServerConfig
    name: str
    title: str | None = None
    description: str = ""
    arguments: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class MCPToolReport:
    server: str
    original_name: str
    model_facing_name: str
    description: str
    read_only: bool
    exposed_by_policy: bool
    requires_approval: bool


class MCPToolLoader:
    def __init__(
        self,
        config_path: Path,
        *,
        selected_servers: Iterable[str] | None = None,
        discovery: Callable[[MCPServerConfig], list[MCPToolDefinition]] | None = None,
        resource_discovery: Callable[[MCPServerConfig], list[MCPResourceDefinition]] | None = None,
        prompt_discovery: Callable[[MCPServerConfig], list[MCPPromptDefinition]] | None = None,
        caller: Callable[[MCPServerConfig, str, dict[str, Any]], Any] | None = None,
    ) -> None:
        self.config_path = config_path
        self.selected_servers = tuple(selected_servers) if selected_servers is not None else None
        self.discovery = discovery
        self.resource_discovery = resource_discovery
        self.prompt_discovery = prompt_discovery
        self.caller = caller

    def load_tools(self) -> list[StructuredTool]:
        tools = []
        seen_model_names: set[str] = set()
        for server in self._selected_server_configs():
            definitions = self._discover(server)
            for definition in definitions:
                if not _is_exposed_by_policy(server, definition.name):
                    continue
                tool = self._to_structured_tool(definition)
                if tool.name in seen_model_names:
                    raise ValueError(f"MCP tool name collision after canonicalization: {tool.name}")
                seen_model_names.add(tool.name)
                tools.append(tool)
        return tools

    def list_tool_reports(self, server_name: str | None = None) -> list[MCPToolReport]:
        reports: list[MCPToolReport] = []
        for server in self._server_configs_for_discovery(server_name):
            for definition in self._discover(server):
                read_only = _is_read_only(server, definition.name)
                reports.append(
                    MCPToolReport(
                        server=server.name,
                        original_name=definition.name,
                        model_facing_name=_model_facing_tool_name(server.name, definition.name),
                        description=definition.description,
                        read_only=read_only,
                        exposed_by_policy=_is_exposed_by_policy(server, definition.name),
                        requires_approval=not read_only,
                    )
                )
        return reports

    def list_servers(self) -> list[MCPServerConfig]:
        return load_mcp_server_configs(self.config_path)

    def list_resources(self, server_name: str | None = None) -> list[MCPResourceDefinition]:
        resources: list[MCPResourceDefinition] = []
        for server in self._server_configs_for_discovery(server_name):
            resources.extend(self._discover_resources(server))
        return resources

    def list_prompts(self, server_name: str | None = None) -> list[MCPPromptDefinition]:
        prompts: list[MCPPromptDefinition] = []
        for server in self._server_configs_for_discovery(server_name):
            prompts.extend(self._discover_prompts(server))
        return prompts

    def _selected_server_configs(self) -> list[MCPServerConfig]:
        if self.selected_servers is None:
            return load_mcp_server_configs(self.config_path)
        configs = load_mcp_server_configs(self.config_path)
        by_name = {config.name: config for config in configs}
        selected = _dedupe(self.selected_servers)
        unknown = [name for name in selected if name not in by_name]
        if unknown:
            raise ValueError(f"unknown selected MCP server(s): {', '.join(unknown)}")
        return [by_name[name] for name in selected]

    def _server_configs_for_discovery(self, server_name: str | None) -> list[MCPServerConfig]:
        configs = load_mcp_server_configs(self.config_path)
        if server_name is None:
            return configs
        for server in configs:
            if server.name == server_name:
                return [server]
        raise ValueError(f"unknown MCP server: {server_name}")

    def _discover(self, server: MCPServerConfig) -> list[MCPToolDefinition]:
        if self.discovery is not None:
            return self.discovery(server)
        return asyncio.run(_discover_stdio_tools(server))

    def _discover_resources(self, server: MCPServerConfig) -> list[MCPResourceDefinition]:
        if self.resource_discovery is not None:
            return self.resource_discovery(server)
        return asyncio.run(_discover_stdio_resources(server))

    def _discover_prompts(self, server: MCPServerConfig) -> list[MCPPromptDefinition]:
        if self.prompt_discovery is not None:
            return self.prompt_discovery(server)
        return asyncio.run(_discover_stdio_prompts(server))

    def _to_structured_tool(self, definition: MCPToolDefinition) -> StructuredTool:
        tool_name = _model_facing_tool_name(definition.server.name, definition.name)
        read_only = _is_read_only(definition.server, definition.name)
        dangerous = not read_only

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
                "source": "mcp",
                "mcp_server": definition.server.name,
                "mcp_tool": definition.name,
                "mcp_model_facing_name": tool_name,
                "mcp_read_only": read_only,
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
        tool_exposure = str(raw.get("tool_exposure") or "read_only")
        if tool_exposure not in TOOL_EXPOSURE_POLICIES:
            raise ValueError(
                f"MCP server '{name}' has unsupported tool_exposure '{tool_exposure}'. "
                f"Expected one of: {', '.join(sorted(TOOL_EXPOSURE_POLICIES))}"
            )
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
                tool_exposure=tool_exposure,
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


async def _discover_stdio_resources(server: MCPServerConfig) -> list[MCPResourceDefinition]:
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
            result = await session.list_resources()
            resources = []
            for resource in result.resources:
                resources.append(
                    MCPResourceDefinition(
                        server=server,
                        uri=str(getattr(resource, "uri", "")),
                        name=str(getattr(resource, "name", "")),
                        title=getattr(resource, "title", None),
                        description=getattr(resource, "description", None) or "",
                        mime_type=getattr(resource, "mimeType", None),
                        size=getattr(resource, "size", None),
                    )
                )
            return resources


async def _discover_stdio_prompts(server: MCPServerConfig) -> list[MCPPromptDefinition]:
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
            result = await session.list_prompts()
            prompts = []
            for prompt in result.prompts:
                prompts.append(
                    MCPPromptDefinition(
                        server=server,
                        name=str(getattr(prompt, "name", "")),
                        title=getattr(prompt, "title", None),
                        description=getattr(prompt, "description", None) or "",
                        arguments=_serialize_prompt_arguments(getattr(prompt, "arguments", None)),
                    )
                )
            return prompts


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


def _serialize_prompt_arguments(arguments: Any) -> list[dict[str, Any]]:
    if not isinstance(arguments, list):
        return []
    serialized = []
    for argument in arguments:
        serialized.append(
            {
                "name": str(getattr(argument, "name", "")),
                "description": getattr(argument, "description", None) or "",
                "required": getattr(argument, "required", None),
            }
        )
    return serialized


def _is_read_only(server: MCPServerConfig, tool_name: str) -> bool:
    if server.read_only:
        return True
    override = server.tool_overrides.get(tool_name)
    if isinstance(override, dict) and override.get("read_only") is True:
        return True
    return tool_name in server.read_only_tools


def _is_exposed_by_policy(server: MCPServerConfig, tool_name: str) -> bool:
    if server.tool_exposure == "none":
        return False
    if server.tool_exposure == "all":
        return True
    if server.tool_exposure == "read_only":
        return _is_read_only(server, tool_name)
    if server.tool_exposure == "allowlist":
        return tool_name in server.tool_overrides
    raise ValueError(f"unsupported MCP tool_exposure: {server.tool_exposure}")


def _model_facing_tool_name(server_name: str, tool_name: str) -> str:
    return f"mcp__{_canonical_name(server_name, 'server')}__{_canonical_name(tool_name, 'tool')}"


def _canonical_name(value: str, label: str) -> str:
    name = re.sub(r"[^a-z0-9_]+", "_", value.lower())
    name = re.sub(r"_+", "_", name).strip("_")
    if not name:
        raise ValueError(f"MCP {label} name is empty after canonicalization: {value!r}")
    return name


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


MCPClientManager = MCPToolLoader
