from __future__ import annotations

from mini_agent.tool_registry import ToolRegistry
from mini_agent.types import ToolSpec

from .constants import KUBECTL_DESCRIBE_RESOURCES, KUBECTL_GET_RESOURCES
from .dangerous import delete_resource, exec_shell, kubectl_apply
from .mock import grep_logs, kubectl_get, read_file
from .remote_kubernetes import ssh_kubectl_describe, ssh_kubectl_get


def register_devops_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="read_file",
            description="Read a file under the project root.",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            dangerous=False,
            func=read_file,
        )
    )
    registry.register(
        ToolSpec(
            name="grep_logs",
            description="Search the mock nginx log for a simple substring. Use 'error' to find error lines.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Simple substring such as 'error', 'timeout', or '502'.",
                    }
                },
                "required": ["pattern"],
            },
            dangerous=False,
            func=grep_logs,
        )
    )
    registry.register(
        ToolSpec(
            name="kubectl_get",
            description="Read mock Kubernetes resource state from local sample data.",
            parameters={
                "type": "object",
                "properties": {"resource": {"type": "string", "enum": ["pods", "services"]}},
                "required": ["resource"],
            },
            dangerous=False,
            func=kubectl_get,
        )
    )
    registry.register(
        ToolSpec(
            name="ssh_kubectl_get",
            description=(
                "Read current real Kubernetes cluster state over SSH. Prefer this for current, real, "
                "remote, or live cluster questions. This is read-only."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "resource": {"type": "string", "enum": KUBECTL_GET_RESOURCES},
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace or 'all'. Defaults to 'all'.",
                    },
                },
                "required": ["resource"],
            },
            dangerous=False,
            func=ssh_kubectl_get,
        )
    )
    registry.register(
        ToolSpec(
            name="ssh_kubectl_describe",
            description=(
                "Describe a Kubernetes resource over SSH. Read-only. Use after ssh_kubectl_get "
                "when detailed status/events are needed."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "resource": {"type": "string", "enum": KUBECTL_DESCRIBE_RESOURCES},
                    "name": {"type": "string"},
                    "namespace": {
                        "type": "string",
                        "description": "Kubernetes namespace. Ignored for node. Defaults to default.",
                    },
                },
                "required": ["resource", "name"],
            },
            dangerous=False,
            func=ssh_kubectl_describe,
        )
    )
    registry.register(
        ToolSpec(
            name="exec_shell",
            description="Execute a shell command. Dangerous and requires approval.",
            parameters={"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
            dangerous=True,
            func=exec_shell,
        )
    )
    registry.register(
        ToolSpec(
            name="kubectl_apply",
            description="Apply a Kubernetes manifest. Dangerous and requires approval.",
            parameters={"type": "object", "properties": {"manifest": {"type": "string"}}, "required": ["manifest"]},
            dangerous=True,
            func=kubectl_apply,
        )
    )
    registry.register(
        ToolSpec(
            name="delete_resource",
            description="Delete a Kubernetes resource. Dangerous and requires approval.",
            parameters={
                "type": "object",
                "properties": {"resource": {"type": "string"}, "name": {"type": "string"}},
                "required": ["resource", "name"],
            },
            dangerous=True,
            func=delete_resource,
        )
    )

