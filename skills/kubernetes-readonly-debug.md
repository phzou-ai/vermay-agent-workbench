---
name: kubernetes-readonly-debug
description: Read-only Kubernetes status inspection using safe cluster query tools.
triggers: k8s, kubernetes, pods, services, cluster
version: 0.1.0
---

Prefer read-only inspection before proposing a fix.

Use service, pod, deployment, node, and event queries to establish current state.
Do not claim a cluster operation completed unless a tool observation confirms it.
Dangerous write operations require explicit approval.
