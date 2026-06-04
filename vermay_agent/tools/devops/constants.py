from __future__ import annotations

from enum import Enum


class KubectlGetResource(str, Enum):
    pods = "pods"
    services = "services"
    deployments = "deployments"
    nodes = "nodes"
    namespaces = "namespaces"
    events = "events"


class MockKubectlGetResource(str, Enum):
    pods = "pods"
    services = "services"


class KubectlDescribeResource(str, Enum):
    pod = "pod"
    service = "service"
    deployment = "deployment"
    node = "node"


KUBECTL_GET_RESOURCES = [resource.value for resource in KubectlGetResource]
MOCK_KUBECTL_GET_RESOURCES = [resource.value for resource in MockKubectlGetResource]
KUBECTL_DESCRIBE_RESOURCES = [resource.value for resource in KubectlDescribeResource]
