from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from vermay_agent.api.task_contract import ARTIFACT_TASK_EVENT_TYPES
from vermay_agent.errors import InvalidRequestError, TaskNotFoundError

from ..service import AgentService
from ..session_store import SessionRecord, TaskEventRecord, TaskRecord
from .agent_card import A2AAgentCardConfig, build_agent_card
from .models import A2AMessage, A2ASendMessageRequest
from .projection import A2AProjectionKind, project_task, project_task_artifact_event, project_task_event


@dataclass(frozen=True)
class A2AAdapterConfig:
    agent_card: A2AAgentCardConfig = field(default_factory=A2AAgentCardConfig)
    message_metadata_allowlist: frozenset[str] = frozenset({"tenant", "client"})


@dataclass(frozen=True)
class A2AEventBatch:
    last_event_id: int
    events: list[dict[str, Any]]


class A2AAdapter:
    def __init__(self, *, service: AgentService, config: A2AAdapterConfig | None = None) -> None:
        self.service = service
        self.config = config or A2AAdapterConfig()

    def get_agent_card(self) -> dict[str, Any]:
        return build_agent_card(self.config.agent_card)

    def send_message(self, request: A2ASendMessageRequest, *, wait: bool = True) -> dict[str, Any]:
        user_input = _extract_user_input(request.message)
        session = self._resolve_session(request.message.context_id, request=request)
        task = self.service.start_task(
            session.session_id,
            user_input,
            task_id=request.message.task_id,
            wait=wait,
        )
        return self.project_task(task)

    def get_task(self, task_id: str) -> dict[str, Any]:
        task = self.service.get_task(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        return self.project_task(task)

    def cancel_task(self, task_id: str, *, reason: str | None = None) -> dict[str, Any]:
        task = self.service.cancel_task(task_id, reason=reason)
        return self.project_task(task)

    def project_task(self, task: TaskRecord) -> dict[str, Any]:
        session = self.service.get_session(task.session_id)
        artifacts = self.service.list_task_artifacts(task.task_id)
        projection = project_task(
            task,
            context_id=session.context_id if session is not None else None,
            artifacts=artifacts,
        )
        if projection.payload is None:
            raise RuntimeError(f"failed to project task: {task.task_id}")
        return projection.payload

    def project_task_events(self, task_id: str, *, after_event_id: int = 0) -> list[dict[str, Any]]:
        events = [event for event in self.service.list_task_events(task_id) if event.event_id > after_event_id]
        return list(self._project_events(events))

    def wait_for_task_events(
        self,
        task_id: str,
        *,
        after_event_id: int,
        timeout_seconds: float,
    ) -> A2AEventBatch:
        events = self.service.wait_for_task_events(
            task_id,
            after_event_id=after_event_id,
            timeout_seconds=timeout_seconds,
        )
        return A2AEventBatch(
            last_event_id=_last_event_id(events, fallback=after_event_id),
            events=list(self._project_events(events)),
        )

    def _resolve_session(self, context_id: str | None, *, request: A2ASendMessageRequest) -> SessionRecord:
        if context_id:
            existing = self.service.get_session_by_context_id(context_id)
            if existing is not None:
                return existing
            return self.service.create_session(
                context_id=context_id,
                metadata=_session_metadata(request, allowlist=self.config.message_metadata_allowlist),
            )
        return self.service.create_session(
            metadata=_session_metadata(request, allowlist=self.config.message_metadata_allowlist),
        )

    def _project_events(self, events: Iterable[TaskEventRecord]) -> Iterable[dict[str, Any]]:
        for event in events:
            artifact_payload = _artifact_event_payload(event)
            if artifact_payload is not None:
                artifact = self.service.get_task_artifact_by_a2a_id(
                    task_id=event.task_id,
                    a2a_artifact_id=artifact_payload["a2a_artifact_id"],
                )
                projection = project_task_artifact_event(event, artifact=artifact)
            else:
                projection = project_task_event(event)
            if projection.kind in {A2AProjectionKind.STATUS_UPDATE, A2AProjectionKind.ARTIFACT_UPDATE}:
                if projection.payload is not None:
                    yield projection.payload


def _extract_user_input(message: A2AMessage) -> str:
    if message.role not in {None, "user"}:
        raise InvalidRequestError("A2A message role must be 'user'.")
    text_parts = [str(part["text"]).strip() for part in message.parts if isinstance(part.get("text"), str)]
    text = "\n".join(part for part in text_parts if part)
    if not text:
        raise InvalidRequestError("A2A message must include at least one text part.")
    return text


def _session_metadata(request: A2ASendMessageRequest, *, allowlist: frozenset[str]) -> dict[str, Any]:
    metadata: dict[str, Any] = {"source": "a2a"}
    for source in (request.metadata, request.message.metadata):
        for key in allowlist:
            if key in source:
                metadata[key] = source[key]
    return metadata


def _artifact_event_payload(event: TaskEventRecord) -> dict[str, Any] | None:
    if event.event_type not in ARTIFACT_TASK_EVENT_TYPES:
        return None
    a2a_artifact_id = event.payload.get("a2a_artifact_id")
    if not isinstance(a2a_artifact_id, str) or not a2a_artifact_id:
        return None
    return {"a2a_artifact_id": a2a_artifact_id}


def _last_event_id(events: list[TaskEventRecord], *, fallback: int) -> int:
    if not events:
        return fallback
    return max(event.event_id for event in events)
