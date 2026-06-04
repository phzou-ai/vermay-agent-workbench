from __future__ import annotations

import json
from pathlib import Path

from .constants import MockKubectlGetResource


ROOT = Path(__file__).resolve().parents[3]


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


def kubectl_get(resource: str | MockKubectlGetResource) -> dict:
    try:
        resource_value = MockKubectlGetResource(resource).value
    except ValueError as exc:
        raise ValueError(f"unsupported mock resource: {resource}") from exc
    cluster = json.loads((ROOT / "data" / "cluster.json").read_text(encoding="utf-8"))
    if resource_value not in cluster:
        raise ValueError(f"unknown mock resource: {resource_value}")
    return {resource_value: cluster[resource_value]}
