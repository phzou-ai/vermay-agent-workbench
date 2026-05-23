from __future__ import annotations

import json
import shlex
from pathlib import Path

from mini_agent.ssh_client import SshClient
from mini_agent.tool_registry import ToolRegistry
from mini_agent.types import ToolSpec


ROOT = Path(__file__).resolve().parents[2]
KUBECTL_GET_RESOURCES = ["pods", "services", "deployments", "nodes", "namespaces", "events"]
KUBECTL_DESCRIBE_RESOURCES = ["pod", "service", "deployment", "node"]


def read_file(path: str) -> str:
    target = (ROOT / path).resolve()
    if ROOT not in target.parents and target != ROOT:
        raise ValueError("path escapes project root")
    return target.read_text(encoding="utf-8")


def grep_logs(pattern: str) -> dict:
    log_path = ROOT / "data" / "nginx.log"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    matches = [line for line in lines if pattern.lower() in line.lower()]
    return {"pattern": pattern, "matches": matches, "count": len(matches)}


def kubectl_get(resource: str) -> dict:
    cluster = json.loads((ROOT / "data" / "cluster.json").read_text(encoding="utf-8"))
    if resource not in cluster:
        raise ValueError(f"unknown mock resource: {resource}")
    return {resource: cluster[resource]}


def ssh_kubectl_get(resource: str, namespace: str = "all") -> dict:
    if resource not in KUBECTL_GET_RESOURCES:
        raise ValueError(f"unsupported resource: {resource}")
    args = ["get", resource]
    if namespace == "all":
        args.append("-A")
    else:
        args.extend(["-n", namespace])
    args.extend(["-o", "wide"])
    command = _remote_kubectl_command(args)
    return SshClient().run(command)


def ssh_kubectl_describe(resource: str, name: str, namespace: str = "default") -> dict:
    if resource not in KUBECTL_DESCRIBE_RESOURCES:
        raise ValueError(f"unsupported resource: {resource}")
    if resource == "node":
        args = ["describe", "node", name]
    else:
        args = ["describe", resource, name, "-n", namespace]
    command = _remote_kubectl_command(args)
    return SshClient(timeout_seconds=30).run(command)


def _remote_kubectl_command(args: list[str]) -> str:
    quoted_args = " ".join(shlex.quote(arg) for arg in args)
    return (
        "PATH=/snap/bin:/usr/local/bin:/usr/bin:/bin:$PATH; "
        "if command -v kubectl >/dev/null 2>&1; then "
        f"kubectl {quoted_args}; "
        "elif command -v microk8s >/dev/null 2>&1; then "
        f"microk8s kubectl {quoted_args}; "
        "elif [ -x /snap/bin/microk8s ]; then "
        f"/snap/bin/microk8s kubectl {quoted_args}; "
        "else "
        "echo 'kubectl not found: tried kubectl, microk8s kubectl, /snap/bin/microk8s kubectl' >&2; "
        "exit 127; "
        "fi"
    )


def exec_shell(command: str) -> dict:
    return {"command": command, "status": "not_executed_in_demo"}


def kubectl_apply(manifest: str) -> dict:
    return {"manifest": manifest, "status": "not_applied_in_demo"}


def delete_resource(resource: str, name: str) -> dict:
    return {"resource": resource, "name": name, "status": "not_deleted_in_demo"}


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
