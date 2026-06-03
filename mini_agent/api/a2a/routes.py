from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from mini_agent.api.a2a_readiness import is_terminal_a2a_state
from mini_agent.errors import error_info_from_exception

from .adapter import A2AAdapter
from .models import A2ACancelTaskRequest, A2ASendMessageRequest


def create_a2a_router(adapter: A2AAdapter) -> APIRouter:
    router = APIRouter()
    router.state = {"adapter": adapter}

    @router.get("/.well-known/agent-card.json")
    def get_agent_card() -> dict[str, Any]:
        return adapter.get_agent_card()

    @router.post("/message:send")
    def send_message(request: A2ASendMessageRequest) -> dict[str, Any]:
        try:
            return adapter.send_message(request)
        except Exception as exc:
            raise _a2a_http_exception(exc) from exc

    @router.get("/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        try:
            return adapter.get_task(task_id)
        except Exception as exc:
            raise _a2a_http_exception(exc) from exc

    @router.post("/tasks/{task_id}:cancel")
    def cancel_task(task_id: str, request: A2ACancelTaskRequest | None = None) -> dict[str, Any]:
        try:
            return adapter.cancel_task(task_id, reason=request.reason if request is not None else None)
        except Exception as exc:
            raise _a2a_http_exception(exc) from exc

    @router.post("/tasks/{task_id}:subscribe")
    async def subscribe_task_events(
        task_id: str,
        request: Request,
        after: int = Query(default=0, ge=0),
    ) -> StreamingResponse:
        try:
            adapter.get_task(task_id)
        except Exception as exc:
            raise _a2a_http_exception(exc) from exc

        async def event_stream():
            last_event_id = after
            while True:
                if await request.is_disconnected():
                    break
                batch = await asyncio.to_thread(
                    adapter.wait_for_task_events,
                    task_id,
                    after_event_id=last_event_id,
                    timeout_seconds=1.0,
                )
                last_event_id = max(last_event_id, batch.last_event_id)
                for event in batch.events:
                    yield _format_a2a_sse_event(event)
                task = adapter.get_task(task_id)
                state = task["task"]["status"]["state"]
                if is_terminal_a2a_state(state):
                    trailing_batch = await asyncio.to_thread(
                        adapter.wait_for_task_events,
                        task_id,
                        after_event_id=last_event_id,
                        timeout_seconds=0.0,
                    )
                    last_event_id = max(last_event_id, trailing_batch.last_event_id)
                    for event in trailing_batch.events:
                        yield _format_a2a_sse_event(event)
                    break

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return router


def _a2a_http_exception(exc: Exception) -> HTTPException:
    error = error_info_from_exception(exc)
    return HTTPException(
        status_code=error.http_status,
        detail={
            "code": error.code.value,
            "message": error.public_message,
        },
    )


def _format_a2a_sse_event(event: dict[str, Any]) -> str:
    event_type = next(iter(event))
    event_id = _event_id(event)
    data = json.dumps(event, ensure_ascii=False, sort_keys=True)
    prefix = f"id: {event_id}\n" if event_id is not None else ""
    return f"{prefix}event: {event_type}\ndata: {data}\n\n"


def _event_id(event: dict[str, Any]) -> int | None:
    body = next(iter(event.values()), None)
    if not isinstance(body, dict):
        return None
    metadata = body.get("metadata")
    if not isinstance(metadata, dict):
        return None
    event_id = metadata.get("localEventId")
    if isinstance(event_id, int):
        return event_id
    return None
