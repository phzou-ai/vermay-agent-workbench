from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class A2AAgentSkillConfig:
    id: str
    name: str
    description: str
    tags: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class A2AAgentCardConfig:
    name: str = "Vermay Agent Workbench"
    description: str = "An experimental local workbench for task-based, resumable agent execution."
    url: str = "http://127.0.0.1:8000"
    version: str = "0.1.0"
    protocol_versions: tuple[str, ...] = ("0.3",)
    default_input_modes: tuple[str, ...] = ("text/plain",)
    default_output_modes: tuple[str, ...] = ("text/plain",)
    streaming: bool = False
    push_notifications: bool = False
    extended_agent_card: bool = False
    skills: tuple[A2AAgentSkillConfig, ...] = field(
        default_factory=lambda: (
            A2AAgentSkillConfig(
                id="agent-task-execution",
                name="Agent task execution",
                description="Run a single agent task and return task status plus artifacts.",
                tags=("agent", "tools", "approval"),
            ),
        )
    )
    security_schemes: dict[str, Any] = field(default_factory=dict)
    security: list[dict[str, Any]] = field(default_factory=list)


def build_agent_card(config: A2AAgentCardConfig | None = None) -> dict[str, Any]:
    active = config or A2AAgentCardConfig()
    return {
        "name": active.name,
        "description": active.description,
        "url": active.url,
        "version": active.version,
        "protocolVersions": list(active.protocol_versions),
        "capabilities": {
            "streaming": active.streaming,
            "pushNotifications": active.push_notifications,
            "extendedAgentCard": active.extended_agent_card,
        },
        "defaultInputModes": list(active.default_input_modes),
        "defaultOutputModes": list(active.default_output_modes),
        "skills": [_skill_payload(skill) for skill in active.skills],
        "securitySchemes": dict(active.security_schemes),
        "security": list(active.security),
    }


def _skill_payload(skill: A2AAgentSkillConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
    }
    if skill.tags:
        payload["tags"] = list(skill.tags)
    if skill.examples:
        payload["examples"] = list(skill.examples)
    return payload
