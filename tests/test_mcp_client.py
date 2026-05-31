from __future__ import annotations

import json

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
    config.write_text(json.dumps({"servers": {"docs": {"transport": "stdio", "command": "server"}}}), encoding="utf-8")

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

    assert tools[0].name == "mcp_docs_search"
    assert tools[0].metadata["dangerous"] is True


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
