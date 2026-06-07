from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .models import MainAgentRequest, RegisteredAgentRecord


@dataclass(frozen=True)
class RemoteAgentSendResult:
    kind: str
    context_id: str | None = None
    message_id: str | None = None
    task_id: str | None = None
    status: str | None = None
    parts: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RemoteAgentTaskSnapshot:
    task_id: str
    context_id: str | None = None
    status: str | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class RemoteAgentClient(Protocol):
    def send_message(
        self,
        *,
        agent: RegisteredAgentRecord,
        request: MainAgentRequest,
        context_id: str,
        message_id: str,
    ) -> RemoteAgentSendResult:
        """Forward a message to a registered child A2A agent."""

    def get_task(self, *, agent: RegisteredAgentRecord, task_id: str) -> RemoteAgentTaskSnapshot:
        """Fetch a remote task snapshot from a registered child A2A agent."""

    def cancel_task(
        self,
        *,
        agent: RegisteredAgentRecord,
        task_id: str,
        reason: str | None = None,
    ) -> RemoteAgentTaskSnapshot:
        """Request remote task cancellation from a registered child A2A agent."""


class DirectA2ARemoteAgentClient:
    def __init__(self, *, timeout_seconds: float = 30.0) -> None:
        self.timeout_seconds = timeout_seconds

    def send_message(
        self,
        *,
        agent: RegisteredAgentRecord,
        request: MainAgentRequest,
        context_id: str,
        message_id: str,
    ) -> RemoteAgentSendResult:
        payload = {
            "jsonrpc": "2.0",
            "id": f"delegate-{message_id}",
            "method": "message/send",
            "params": {
                "message": {
                    "kind": "message",
                    "role": request.role.value,
                    "messageId": message_id,
                    "contextId": context_id,
                    "parts": request.parts,
                },
                "metadata": _forward_metadata(request.metadata, context_id=context_id),
            },
        }
        http_request = Request(
            _message_send_url(agent.card_url),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urlopen(http_request, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
        result = body.get("result")
        if not isinstance(result, dict):
            raise ValueError("remote agent response missing JSON-RPC result")
        return _remote_result_from_payload(result, raw=body)

    def get_task(self, *, agent: RegisteredAgentRecord, task_id: str) -> RemoteAgentTaskSnapshot:
        with urlopen(
            Request(
                _task_url(agent.card_url, task_id),
                headers={"Accept": "application/json"},
                method="GET",
            ),
            timeout=self.timeout_seconds,
        ) as response:
            body = json.loads(response.read().decode("utf-8"))
        return _remote_task_snapshot_from_body(body, fallback_task_id=task_id)

    def cancel_task(
        self,
        *,
        agent: RegisteredAgentRecord,
        task_id: str,
        reason: str | None = None,
    ) -> RemoteAgentTaskSnapshot:
        payload = {"reason": reason} if reason else {}
        http_request = Request(
            _task_cancel_url(agent.card_url, task_id),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urlopen(http_request, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
        return _remote_task_snapshot_from_body(body, fallback_task_id=task_id)


def fetch_agent_card(card_url: str, *, timeout_seconds: float = 10.0) -> dict[str, Any]:
    with urlopen(
        Request(card_url, headers={"Accept": "application/json"}, method="GET"),
        timeout=timeout_seconds,
    ) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not isinstance(body, dict):
        raise ValueError("agent card response must be a JSON object")
    return body


def _message_send_url(card_url: str) -> str:
    return _root_url(card_url).rstrip("/") + "/message:send"


def _task_url(card_url: str, task_id: str) -> str:
    return _root_url(card_url).rstrip("/") + f"/tasks/{quote(task_id, safe='')}"


def _task_cancel_url(card_url: str, task_id: str) -> str:
    return _root_url(card_url).rstrip("/") + f"/tasks/{quote(task_id, safe='')}:cancel"


def _root_url(card_url: str) -> str:
    parsed = urlsplit(card_url)
    path = parsed.path
    marker = "/.well-known/agent-card.json"
    if path.endswith(marker):
        path = path[: -len(marker)]
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _remote_result_from_payload(result: dict[str, Any], *, raw: dict[str, Any]) -> RemoteAgentSendResult:
    kind = str(result.get("kind") or "")
    if kind == "message":
        return RemoteAgentSendResult(
            kind="message",
            context_id=_optional_str(result.get("contextId")),
            message_id=_optional_str(result.get("messageId")),
            parts=list(result.get("parts") or []),
            raw=raw,
        )
    if kind == "task":
        status = result.get("status") if isinstance(result.get("status"), dict) else {}
        return RemoteAgentSendResult(
            kind="task",
            context_id=_optional_str(result.get("contextId")),
            task_id=_optional_str(result.get("id")),
            status=_optional_str(status.get("state")),
            raw=raw,
        )
    raise ValueError(f"unsupported remote agent result kind: {kind}")


def _remote_task_snapshot_from_body(body: dict[str, Any], *, fallback_task_id: str) -> RemoteAgentTaskSnapshot:
    result = body.get("result") if isinstance(body.get("result"), dict) else body
    if not isinstance(result, dict):
        raise ValueError("remote agent task response missing task payload")
    task = result.get("task") if isinstance(result.get("task"), dict) else result
    if not isinstance(task, dict):
        raise ValueError("remote agent task response missing task object")
    status = task.get("status") if isinstance(task.get("status"), dict) else {}
    artifacts = task.get("artifacts") if isinstance(task.get("artifacts"), list) else []
    return RemoteAgentTaskSnapshot(
        task_id=_optional_str(task.get("id")) or fallback_task_id,
        context_id=_optional_str(task.get("contextId")),
        status=_optional_str(status.get("state")),
        artifacts=list(artifacts),
        raw=body,
    )


def _forward_metadata(metadata: dict[str, object], *, context_id: str) -> dict[str, Any]:
    forwarded: dict[str, Any] = {
        "delegatedBy": "vermay-main-agent",
        "sourceContextId": context_id,
    }
    execution_mode = metadata.get("executionMode")
    if isinstance(execution_mode, str) and execution_mode:
        forwarded["executionMode"] = execution_mode
    return forwarded


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
