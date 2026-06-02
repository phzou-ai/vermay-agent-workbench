from __future__ import annotations

import pytest

from mini_agent.mcp_selection import MCPSelectionConfig


def test_mcp_selection_normalizes_payload():
    selection = MCPSelectionConfig.from_payload(
        {
            "servers": ["k8s", "k8s"],
            "prompts": [{"server": "k8s", "name": "debug"}],
            "resources": [{"server": "k8s", "uri": "k8s://cluster/services"}],
        }
    )

    assert selection is not None
    assert selection.servers == ("k8s",)
    assert selection.to_runtime_prompts() == ("k8s:debug",)
    assert selection.to_runtime_resources() == ("k8s:k8s://cluster/services",)
    assert selection.to_payload() == {
        "servers": ["k8s"],
        "prompts": [{"server": "k8s", "name": "debug"}],
        "resources": [{"server": "k8s", "uri": "k8s://cluster/services"}],
    }


def test_mcp_selection_rejects_non_list_servers():
    with pytest.raises(ValueError, match="MCP servers must be a list"):
        MCPSelectionConfig.from_payload({"servers": "k8s"})


def test_mcp_selection_rejects_prompt_for_unselected_server():
    with pytest.raises(ValueError, match="unselected server"):
        MCPSelectionConfig.from_payload(
            {
                "servers": ["docs"],
                "prompts": [{"server": "k8s", "name": "debug"}],
            }
        )
