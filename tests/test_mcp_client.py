from __future__ import annotations

import json

import pytest

from mini_agent.mcp_client import MCPToolDefinition, MCPToolLoader, load_mcp_server_configs


def test_mcp_config_parser_reads_stdio_servers(tmp_path):
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "servers": {
                    "docs": {
                        "transport": "stdio",
                        "command": "python",
                        "args": ["server.py"],
                        "read_only_tools": ["search"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    servers = load_mcp_server_configs(config)

    assert servers[0].name == "docs"
    assert servers[0].command == "python"
    assert servers[0].read_only_tools == {"search"}


def test_mcp_tools_are_approval_required_by_default(tmp_path):
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "servers": {
                    "docs": {
                        "transport": "stdio",
                        "command": "server",
                        "tool_exposure": "all",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    def discover(server):
        return [
            MCPToolDefinition(
                name="search",
                description="Search docs.",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
                server=server,
            )
        ]

    tools = MCPToolLoader(config, discovery=discover, caller=lambda server, name, args: {"ok": True}).load_tools()

    assert tools[0].name == "mcp__docs__search"
    assert tools[0].metadata["dangerous"] is True
    assert tools[0].metadata["mcp_server"] == "docs"
    assert tools[0].metadata["mcp_tool"] == "search"


def test_mcp_read_only_config_bypasses_approval(tmp_path):
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "servers": {
                    "docs": {
                        "transport": "stdio",
                        "command": "server",
                        "tools": {"search": {"read_only": True}},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    def discover(server):
        return [
            MCPToolDefinition(
                name="search",
                description="Search docs.",
                input_schema={"type": "object", "properties": {}},
                server=server,
            )
        ]

    tools = MCPToolLoader(config, discovery=discover, caller=lambda server, name, args: "ok").load_tools()

    assert tools[0].metadata["dangerous"] is False


def test_mcp_runtime_selection_can_load_no_servers(tmp_path):
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "servers": {
                    "docs": {
                        "transport": "stdio",
                        "command": "server",
                        "read_only": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    tools = MCPToolLoader(config, selected_servers=[], discovery=lambda server: []).load_tools()

    assert tools == []


def test_mcp_runtime_selection_rejects_unknown_server(tmp_path):
    config = tmp_path / "mcp_servers.json"
    config.write_text(json.dumps({"servers": {"docs": {"transport": "stdio", "command": "server"}}}), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown selected MCP server"):
        MCPToolLoader(config, selected_servers=["missing"], discovery=lambda server: []).load_tools()


def test_mcp_default_read_only_exposure_skips_dangerous_tools(tmp_path):
    config = tmp_path / "mcp_servers.json"
    config.write_text(json.dumps({"servers": {"docs": {"transport": "stdio", "command": "server"}}}), encoding="utf-8")

    def discover(server):
        return [
            MCPToolDefinition(
                name="write",
                description="Write docs.",
                input_schema={"type": "object", "properties": {}},
                server=server,
            )
        ]

    tools = MCPToolLoader(config, selected_servers=["docs"], discovery=discover).load_tools()

    assert tools == []


def test_mcp_allowlist_uses_original_tool_names(tmp_path):
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "servers": {
                    "docs": {
                        "transport": "stdio",
                        "command": "server",
                        "tool_exposure": "allowlist",
                        "tools": {"search.docs": {"read_only": True}},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    def discover(server):
        return [
            MCPToolDefinition(
                name="search.docs",
                description="Search docs.",
                input_schema={"type": "object", "properties": {}},
                server=server,
            ),
            MCPToolDefinition(
                name="other",
                description="Other tool.",
                input_schema={"type": "object", "properties": {}},
                server=server,
            ),
        ]

    tools = MCPToolLoader(config, selected_servers=["docs"], discovery=discover).load_tools()

    assert [tool.name for tool in tools] == ["mcp__docs__search_docs"]
    assert tools[0].metadata["dangerous"] is False


def test_mcp_tool_name_collision_after_canonicalization_fails(tmp_path):
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "servers": {
                    "docs": {
                        "transport": "stdio",
                        "command": "server",
                        "tool_exposure": "all",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    def discover(server):
        return [
            MCPToolDefinition(
                name="search-docs",
                description="Search docs.",
                input_schema={"type": "object", "properties": {}},
                server=server,
            ),
            MCPToolDefinition(
                name="search/docs",
                description="Search docs.",
                input_schema={"type": "object", "properties": {}},
                server=server,
            ),
        ]

    with pytest.raises(ValueError, match="collision"):
        MCPToolLoader(config, selected_servers=["docs"], discovery=discover).load_tools()


def test_mcp_tool_reports_include_policy_fields(tmp_path):
    config = tmp_path / "mcp_servers.json"
    config.write_text(
        json.dumps(
            {
                "servers": {
                    "Docs Server": {
                        "transport": "stdio",
                        "command": "server",
                        "tools": {"search": {"read_only": True}},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    def discover(server):
        return [
            MCPToolDefinition(
                name="search",
                description="Search docs.",
                input_schema={"type": "object", "properties": {}},
                server=server,
            ),
            MCPToolDefinition(
                name="write",
                description="Write docs.",
                input_schema={"type": "object", "properties": {}},
                server=server,
            ),
        ]

    reports = MCPToolLoader(config, discovery=discover).list_tool_reports(server_name="Docs Server")

    assert reports[0].original_name == "search"
    assert reports[0].model_facing_name == "mcp__docs_server__search"
    assert reports[0].read_only is True
    assert reports[0].exposed_by_policy is True
    assert reports[0].requires_approval is False
    assert reports[1].original_name == "write"
    assert reports[1].exposed_by_policy is False
    assert reports[1].requires_approval is True
