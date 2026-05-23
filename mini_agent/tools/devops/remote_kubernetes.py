from __future__ import annotations

import shlex

from mini_agent.infra.ssh import SshClient

from .constants import KUBECTL_DESCRIBE_RESOURCES, KUBECTL_GET_RESOURCES


def ssh_kubectl_get(resource: str, namespace: str = "all") -> dict:
    if resource not in KUBECTL_GET_RESOURCES:
        raise ValueError(f"unsupported resource: {resource}")
    args = ["get", resource]
    if namespace == "all":
        args.append("-A")
    else:
        args.extend(["-n", namespace])
    args.extend(["-o", "wide"])
    command = remote_kubectl_command(args)
    return SshClient().run(command)


def ssh_kubectl_describe(resource: str, name: str, namespace: str = "default") -> dict:
    if resource not in KUBECTL_DESCRIBE_RESOURCES:
        raise ValueError(f"unsupported resource: {resource}")
    if resource == "node":
        args = ["describe", "node", name]
    else:
        args = ["describe", resource, name, "-n", namespace]
    command = remote_kubectl_command(args)
    return SshClient(timeout_seconds=30).run(command)


def remote_kubectl_command(args: list[str]) -> str:
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

