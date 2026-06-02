from __future__ import annotations

from pathlib import Path

from mini_agent.mcp_client import MCPClientManager


def test_tracked_k8s_mcp_config_discovers_example_server_capabilities():
    manager = MCPClientManager(Path("config/mcp_servers.json"))

    reports = manager.list_tool_reports("k8s")
    resources = manager.list_resources("k8s")
    prompts = manager.list_prompts("k8s")

    assert {report.original_name for report in reports} == {"kubectl_get", "kubectl_describe", "cluster_events"}
    assert all(report.read_only is True for report in reports)
    assert all(report.requires_approval is False for report in reports)
    assert {resource.uri for resource in resources} == {
        "k8s://cluster/nodes",
        "k8s://cluster/services",
        "k8s://namespace/{namespace}/pods",
    }
    assert {resource.uri for resource in resources if resource.is_template} == {"k8s://namespace/{namespace}/pods"}
    assert {prompt.name for prompt in prompts} == {"k8s-readonly-debug", "k8s-service-health-check"}
