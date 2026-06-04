from __future__ import annotations

from vermay_agent.tool_registry import ToolRegistry
from vermay_agent.tooling import ToolArgs, structured_tool
from pydantic import Field

from .constants import KubectlDescribeResource, KubectlGetResource, MockKubectlGetResource
from .dangerous import delete_resource, exec_shell, kubectl_apply
from .mock import grep_logs, kubectl_get, read_file
from .remote_kubernetes import ssh_kubectl_describe, ssh_kubectl_get


class ReadFileArgs(ToolArgs):
    path: str = Field(description="Path under the project root.")


class GrepLogsArgs(ToolArgs):
    pattern: str = Field(description="Simple substring such as 'error', 'timeout', or '502'.")


class KubectlGetArgs(ToolArgs):
    resource: MockKubectlGetResource = Field(description="Mock Kubernetes resource type.")


class SshKubectlGetArgs(ToolArgs):
    resource: KubectlGetResource = Field(description="Kubernetes resource type to read.")
    namespace: str = Field(default="all", description="Kubernetes namespace or 'all'.")


class SshKubectlDescribeArgs(ToolArgs):
    resource: KubectlDescribeResource = Field(description="Kubernetes resource type to describe.")
    name: str = Field(description="Kubernetes resource name.")
    namespace: str = Field(default="default", description="Kubernetes namespace. Ignored for node.")


class ExecShellArgs(ToolArgs):
    command: str = Field(description="Shell command to execute.")


class KubectlApplyArgs(ToolArgs):
    manifest: str = Field(description="Kubernetes manifest YAML or JSON.")


class DeleteResourceArgs(ToolArgs):
    resource: str = Field(description="Kubernetes resource type.")
    name: str = Field(description="Kubernetes resource name.")


def register_devops_tools(registry: ToolRegistry) -> None:
    registry.register(
        structured_tool(
            func=read_file,
            name="read_file",
            description="Read a file under the project root.",
            args_schema=ReadFileArgs,
            dangerous=False,
        )
    )
    registry.register(
        structured_tool(
            func=grep_logs,
            name="grep_logs",
            description="Search the mock nginx log for a simple substring. Use 'error' to find error lines.",
            args_schema=GrepLogsArgs,
            dangerous=False,
        )
    )
    registry.register(
        structured_tool(
            func=kubectl_get,
            name="kubectl_get",
            description="Read mock Kubernetes resource state from local sample data.",
            args_schema=KubectlGetArgs,
            dangerous=False,
        )
    )
    registry.register(
        structured_tool(
            func=ssh_kubectl_get,
            name="ssh_kubectl_get",
            description=(
                "Read current real Kubernetes cluster state over SSH. Prefer this for current, real, "
                "remote, or live cluster questions. This is read-only."
            ),
            args_schema=SshKubectlGetArgs,
            dangerous=False,
        )
    )
    registry.register(
        structured_tool(
            func=ssh_kubectl_describe,
            name="ssh_kubectl_describe",
            description=(
                "Describe a Kubernetes resource over SSH. Read-only. Use after ssh_kubectl_get "
                "when detailed status/events are needed."
            ),
            args_schema=SshKubectlDescribeArgs,
            dangerous=False,
        )
    )
    registry.register(
        structured_tool(
            func=exec_shell,
            name="exec_shell",
            description="Execute a shell command. Dangerous and requires approval.",
            args_schema=ExecShellArgs,
            dangerous=True,
        )
    )
    registry.register(
        structured_tool(
            func=kubectl_apply,
            name="kubectl_apply",
            description="Apply a Kubernetes manifest. Dangerous and requires approval.",
            args_schema=KubectlApplyArgs,
            dangerous=True,
        )
    )
    registry.register(
        structured_tool(
            func=delete_resource,
            name="delete_resource",
            description="Delete a Kubernetes resource. Dangerous and requires approval.",
            args_schema=DeleteResourceArgs,
            dangerous=True,
        )
    )
