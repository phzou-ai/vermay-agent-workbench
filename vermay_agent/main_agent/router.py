from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .models import MainAgentRequest, MessageRecord, RouteDecisionKind
from .store import MainAgentStore


@dataclass(frozen=True)
class MainAgentRouteDecision:
    kind: RouteDecisionKind
    reason: str
    confidence: float | None = None
    target_agent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class MainAgentRouter(Protocol):
    def decide(
        self,
        *,
        request: MainAgentRequest,
        context_id: str,
        input_message_id: str,
        messages: list[MessageRecord],
        store: MainAgentStore,
    ) -> MainAgentRouteDecision:
        """Return a protocol-independent route decision for one user message."""


class DefaultMainAgentRouter:
    def decide(
        self,
        *,
        request: MainAgentRequest,
        context_id: str,
        input_message_id: str,
        messages: list[MessageRecord],
        store: MainAgentStore,
    ) -> MainAgentRouteDecision:
        metadata = request.metadata
        explicit = _explicit_route(metadata)
        if explicit is not None:
            if explicit == RouteDecisionKind.REMOTE_AGENT:
                target_agent_id = _target_agent_id(metadata)
                if target_agent_id is None:
                    raise ValueError("remote_agent route requires metadata.targetAgentId")
                return MainAgentRouteDecision(
                    kind=RouteDecisionKind.REMOTE_AGENT,
                    reason=_reason(metadata, fallback="metadata requested remote agent"),
                    confidence=_confidence(metadata),
                    target_agent_id=target_agent_id,
                    metadata={"source": "metadata"},
                )
            return MainAgentRouteDecision(
                kind=explicit,
                reason=_reason(metadata, fallback=f"metadata requested {explicit.value}"),
                confidence=_confidence(metadata),
                metadata={"source": "metadata"},
            )

        execution_mode = str(metadata.get("executionMode") or "auto")
        if execution_mode == "message":
            return MainAgentRouteDecision(
                kind=RouteDecisionKind.LOCAL_MESSAGE,
                reason=_reason(metadata, fallback="executionMode requested message"),
                confidence=_confidence(metadata),
                metadata={"source": "execution_mode"},
            )
        if execution_mode == "task":
            return MainAgentRouteDecision(
                kind=RouteDecisionKind.LOCAL_TASK,
                reason=_reason(metadata, fallback="executionMode requested task"),
                confidence=_confidence(metadata),
                metadata={"source": "execution_mode"},
            )
        if execution_mode != "auto":
            raise ValueError(f"unsupported executionMode: {execution_mode}")

        matched_agent = _match_registered_agent(_text_from_messages(messages), store=store)
        if matched_agent is not None:
            return MainAgentRouteDecision(
                kind=RouteDecisionKind.REMOTE_AGENT,
                reason=f"auto route matched registered agent keyword: {matched_agent['keyword']}",
                confidence=0.7,
                target_agent_id=str(matched_agent["agent_id"]),
                metadata={"source": "keyword_match", "keyword": matched_agent["keyword"]},
            )

        return MainAgentRouteDecision(
            kind=RouteDecisionKind.LOCAL_TASK,
            reason="auto fallback to local task",
            metadata={"source": "auto_fallback"},
        )


def _explicit_route(metadata: dict[str, object]) -> RouteDecisionKind | None:
    route = metadata.get("route")
    if route == "remote_agent":
        return RouteDecisionKind.REMOTE_AGENT
    if route in {"local_message", "local_task"}:
        return RouteDecisionKind(str(route))
    return None


def _target_agent_id(metadata: dict[str, object]) -> str | None:
    for key in ("targetAgentId", "target_agent_id", "remoteAgentId", "remote_agent_id"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _reason(metadata: dict[str, object], *, fallback: str) -> str:
    value = metadata.get("routeReason")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _confidence(metadata: dict[str, object]) -> float | None:
    value = metadata.get("routeConfidence")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _text_from_messages(messages: list[MessageRecord]) -> str:
    text_parts: list[str] = []
    for message in messages:
        for part in message.parts:
            text = part.get("text")
            if isinstance(text, str):
                text_parts.append(text)
    return "\n".join(text_parts).lower()


def _match_registered_agent(text: str, *, store: MainAgentStore) -> dict[str, str] | None:
    if not text.strip():
        return None
    for agent in store.list_registered_agents(enabled_only=True):
        for keyword in _agent_keywords(agent.card_json, agent.metadata):
            normalized = keyword.strip().lower()
            if normalized and normalized in text:
                return {"agent_id": agent.agent_id, "keyword": keyword}
    return None


def _agent_keywords(card_json: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    keywords: list[str] = []
    keywords.extend(_string_list(metadata.get("keywords")))
    keywords.extend(_string_list(card_json.get("keywords")))
    skills = card_json.get("skills")
    if isinstance(skills, list):
        for skill in skills:
            if not isinstance(skill, dict):
                continue
            keywords.extend(_string_list(skill.get("tags")))
    return _dedupe(keywords)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
