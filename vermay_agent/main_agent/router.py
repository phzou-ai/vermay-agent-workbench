from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage

from vermay_agent.langgraph_runtime.nodes import ModelClient

from .models import MainAgentRequest, MessageRecord, RegisteredAgentRecord, RouteDecisionKind, TaskStatus
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


@dataclass(frozen=True)
class RouterModelDecision:
    kind: RouteDecisionKind
    reason: str
    confidence: float | None = None
    target_agent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class RouterModelClient(Protocol):
    def classify(
        self,
        *,
        request: MainAgentRequest,
        messages: list[MessageRecord],
        registered_agents: list[RegisteredAgentRecord],
    ) -> RouterModelDecision:
        """Classify an auto-mode message into a main-agent route."""


class DirectModelRouterModelClient:
    def __init__(self, model: ModelClient, *, confidence_threshold: float = 0.65, model_name: str | None = None) -> None:
        self.model = model
        self.confidence_threshold = confidence_threshold
        self.model_name = model_name

    def classify(
        self,
        *,
        request: MainAgentRequest,
        messages: list[MessageRecord],
        registered_agents: list[RegisteredAgentRecord],
    ) -> RouterModelDecision:
        invocation = self.model.invoke(
            messages=[
                SystemMessage(content=_router_system_prompt(registered_agents)),
                HumanMessage(content=_router_user_prompt(messages)),
            ],
            tools=[],
        )
        raw_content = _string_content(invocation.message.content)
        try:
            payload = _extract_json_object(raw_content)
            decision = _router_model_decision_from_payload(payload, registered_agents=registered_agents)
        except ValueError as exc:
            return _fallback_local_message(
                reason="router model output was invalid",
                metadata={
                    "source": "fallback",
                    "fallbackReason": str(exc),
                    "routerModelRaw": raw_content,
                    **({"model": self.model_name} if self.model_name else {}),
                },
            )

        metadata = {
            "source": "model",
            "model": self.model_name,
            **decision.metadata,
        }
        if decision.confidence is not None and decision.confidence < self.confidence_threshold:
            return _fallback_local_message(
                reason="router model confidence below threshold",
                confidence=decision.confidence,
                metadata={
                    "source": "fallback",
                    "fallbackReason": "low_confidence",
                    "modelRoute": decision.kind.value,
                    "modelReason": decision.reason,
                    "confidenceThreshold": self.confidence_threshold,
                    **({"model": self.model_name} if self.model_name else {}),
                },
            )
        return RouterModelDecision(
            kind=decision.kind,
            reason=decision.reason,
            confidence=decision.confidence,
            target_agent_id=decision.target_agent_id,
            metadata={key: value for key, value in metadata.items() if value is not None},
        )


class DefaultMainAgentRouter:
    def __init__(self, router_model: RouterModelClient | None = None, *, confidence_threshold: float = 0.65) -> None:
        self.router_model = router_model
        self.confidence_threshold = confidence_threshold

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
        execution_mode = str(metadata.get("executionMode") or "auto")
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
                    metadata=_decision_metadata("explicit", executionMode=execution_mode),
                )
            return MainAgentRouteDecision(
                kind=explicit,
                reason=_reason(metadata, fallback=f"metadata requested {explicit.value}"),
                confidence=_confidence(metadata),
                metadata=_decision_metadata("explicit", executionMode=execution_mode),
            )

        if execution_mode == "message":
            return MainAgentRouteDecision(
                kind=RouteDecisionKind.LOCAL_MESSAGE,
                reason=_reason(metadata, fallback="executionMode requested message"),
                confidence=_confidence(metadata),
                metadata=_decision_metadata("explicit", executionMode=execution_mode),
            )
        if execution_mode == "task":
            return MainAgentRouteDecision(
                kind=RouteDecisionKind.LOCAL_TASK,
                reason=_reason(metadata, fallback="executionMode requested task"),
                confidence=_confidence(metadata),
                metadata=_decision_metadata("explicit", executionMode=execution_mode),
            )
        if execution_mode != "auto":
            raise ValueError(f"unsupported executionMode: {execution_mode}")

        hard_signal = _hard_signal_route(metadata, store=store)
        if hard_signal is not None:
            return hard_signal

        matched_agent = _match_registered_agent(_text_from_messages(messages), store=store)
        if matched_agent is not None:
            return MainAgentRouteDecision(
                kind=RouteDecisionKind.REMOTE_AGENT,
                reason=f"auto route matched registered agent keyword: {matched_agent['keyword']}",
                confidence=0.7,
                target_agent_id=str(matched_agent["agent_id"]),
                metadata=_decision_metadata(
                    "guardrail",
                    executionMode=execution_mode,
                    keyword=matched_agent["keyword"],
                    legacySource="keyword_match",
                ),
            )

        if self.router_model is not None:
            model_decision = self.router_model.classify(
                request=request,
                messages=messages,
                registered_agents=store.list_registered_agents(enabled_only=True),
            )
            if (
                model_decision.confidence is not None
                and model_decision.confidence < self.confidence_threshold
                and model_decision.kind != RouteDecisionKind.LOCAL_MESSAGE
            ):
                return _fallback_local_message(
                    reason="router model confidence below threshold",
                    confidence=model_decision.confidence,
                    metadata={
                        "source": "fallback",
                        "executionMode": execution_mode,
                        "fallbackReason": "low_confidence",
                        "modelRoute": model_decision.kind.value,
                        "modelReason": model_decision.reason,
                        "confidenceThreshold": self.confidence_threshold,
                    },
                )
            if model_decision.kind == RouteDecisionKind.REMOTE_AGENT:
                target_agent_id = model_decision.target_agent_id
                if target_agent_id is None or store.get_registered_agent(target_agent_id) is None:
                    return _fallback_local_message(
                        reason="router model selected unknown remote agent",
                        confidence=model_decision.confidence,
                        metadata={
                            "source": "fallback",
                            "fallbackReason": "unknown_remote_agent",
                            "modelRoute": model_decision.kind.value,
                            "modelTargetAgentId": target_agent_id,
                            "modelReason": model_decision.reason,
                        },
                    )
            return MainAgentRouteDecision(
                kind=model_decision.kind,
                reason=model_decision.reason,
                confidence=model_decision.confidence,
                target_agent_id=model_decision.target_agent_id,
                metadata={
                    **_decision_metadata("model", executionMode=execution_mode),
                    **model_decision.metadata,
                },
            )

        return _fallback_local_message(reason="auto fallback to local message")


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


def _hard_signal_route(metadata: dict[str, object], *, store: MainAgentStore) -> MainAgentRouteDecision | None:
    task_id = _metadata_string(metadata, "taskId", "task_id", "localTaskId", "local_task_id")
    if task_id is not None:
        task = store.get_task(task_id)
        if task is not None and task.status not in {TaskStatus.COMPLETED, TaskStatus.CANCELED, TaskStatus.FAILED}:
            return MainAgentRouteDecision(
                kind=RouteDecisionKind.LOCAL_TASK,
                reason=f"auto route continues active task: {task_id}",
                confidence=1.0,
                metadata=_decision_metadata(
                    "hard_signal",
                    executionMode="auto",
                    taskId=task_id,
                    signal="active_task",
                ),
            )

    intent = _metadata_string(metadata, "taskAction", "task_action", "action")
    if intent in {"cancel", "retry", "resume", "approve"}:
        return MainAgentRouteDecision(
            kind=RouteDecisionKind.LOCAL_TASK,
            reason=f"auto route matched task lifecycle action: {intent}",
            confidence=1.0,
            metadata=_decision_metadata(
                "hard_signal",
                executionMode="auto",
                signal="task_lifecycle_action",
                taskAction=intent,
            ),
        )
    return None


def _metadata_string(metadata: dict[str, object], *keys: str) -> str | None:
    for key in keys:
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


def _decision_metadata(source: str, **values: object) -> dict[str, Any]:
    metadata: dict[str, Any] = {"source": source}
    for key, value in values.items():
        if value is not None:
            metadata[key] = value
    return metadata


def _fallback_local_message(
    *,
    reason: str,
    confidence: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> MainAgentRouteDecision | RouterModelDecision:
    return MainAgentRouteDecision(
        kind=RouteDecisionKind.LOCAL_MESSAGE,
        reason=reason,
        confidence=confidence,
        metadata=metadata or _decision_metadata("fallback", executionMode="auto"),
    )


def _text_from_messages(messages: list[MessageRecord]) -> str:
    text_parts: list[str] = []
    for message in messages:
        for part in message.parts:
            text = part.get("text")
            if isinstance(text, str):
                text_parts.append(text)
    return "\n".join(text_parts).lower()


def _router_system_prompt(registered_agents: list[RegisteredAgentRecord]) -> str:
    agents = [
        {
            "agentId": agent.agent_id,
            "name": agent.name,
            "keywords": _agent_keywords(agent.card_json, agent.metadata),
            "skills": _agent_skill_summaries(agent.card_json),
        }
        for agent in registered_agents
        if agent.enabled
    ]
    return (
        "You are a strict route classifier for an A2A main agent. "
        "Choose exactly one route: local_message, local_task, or remote_agent. "
        "Use local_message for direct answers, chat, jokes, explanations, summaries, translations, "
        "and questions about conversation history. "
        "Use local_task only when tools, MCP, SSH, Kubernetes, database/file/shell access, artifacts, "
        "long-running execution, cancel/retry/resume, approval, or stateful operational workflow are needed. "
        "Use remote_agent only when one enabled registered child agent clearly owns the request. "
        "Return only one JSON object with keys route, confidence, reason, and targetAgentId. "
        f"Enabled registered agents: {json.dumps(agents, ensure_ascii=False)}"
    )


def _router_user_prompt(messages: list[MessageRecord]) -> str:
    payload = [
        {
            "role": message.role.value,
            "text": _text_from_parts(message.parts),
        }
        for message in messages[-10:]
    ]
    return json.dumps({"recentMessages": payload}, ensure_ascii=False)


def _text_from_parts(parts: list[dict[str, Any]]) -> str:
    return "\n".join(str(part.get("text", "")).strip() for part in parts if isinstance(part.get("text"), str)).strip()


def _string_content(content: object) -> str:
    if isinstance(content, str):
        return content
    return str(content)


def _extract_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if not text:
        raise ValueError("empty output")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("missing JSON object") from None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("router output must be an object")
    return payload


def _router_model_decision_from_payload(
    payload: dict[str, Any],
    *,
    registered_agents: list[RegisteredAgentRecord],
) -> RouterModelDecision:
    route = payload.get("route")
    if route not in {kind.value for kind in RouteDecisionKind}:
        raise ValueError(f"unsupported route: {route}")
    confidence = payload.get("confidence")
    if confidence is not None and not isinstance(confidence, (int, float)):
        raise ValueError("confidence must be numeric")
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason is required")
    target_agent_id = payload.get("targetAgentId") or payload.get("target_agent_id")
    if target_agent_id is not None and not isinstance(target_agent_id, str):
        raise ValueError("targetAgentId must be a string")
    if route == RouteDecisionKind.REMOTE_AGENT.value:
        enabled_agent_ids = {agent.agent_id for agent in registered_agents if agent.enabled}
        if not target_agent_id:
            raise ValueError("remote_agent requires targetAgentId")
        if target_agent_id not in enabled_agent_ids:
            raise ValueError(f"unknown targetAgentId: {target_agent_id}")
    return RouterModelDecision(
        kind=RouteDecisionKind(route),
        reason=reason.strip(),
        confidence=float(confidence) if confidence is not None else None,
        target_agent_id=target_agent_id.strip() if isinstance(target_agent_id, str) and target_agent_id.strip() else None,
        metadata={"modelReason": reason.strip()},
    )


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


def _agent_skill_summaries(card_json: dict[str, Any]) -> list[dict[str, Any]]:
    skills = card_json.get("skills")
    if not isinstance(skills, list):
        return []
    summaries: list[dict[str, Any]] = []
    for skill in skills:
        if not isinstance(skill, dict):
            continue
        summaries.append(
            {
                "id": skill.get("id"),
                "name": skill.get("name"),
                "description": skill.get("description"),
                "tags": _string_list(skill.get("tags")),
            }
        )
    return summaries


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
