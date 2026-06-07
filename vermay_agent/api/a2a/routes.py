from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from vermay_agent.errors import AgentErrorCode, error_info_from_exception

from .adapter import A2AAdapter
from .projection import is_terminal_a2a_state


def create_a2a_router(adapter: A2AAdapter) -> APIRouter:
    router = APIRouter()
    router.state = {"adapter": adapter}

    @router.get("/.well-known/agent-card.json")
    def get_agent_card() -> dict[str, Any]:
        return adapter.get_agent_card()

    @router.post("/rpc", response_model=None)
    async def rpc(request: Request) -> dict[str, Any] | JSONResponse | StreamingResponse:
        rpc_request = await _parse_rpc_request(request)
        if rpc_request.error is not None:
            return rpc_request.error
        payload = rpc_request.payload
        assert payload is not None
        request_id = payload.get("id")
        method = payload.get("method")
        try:
            if method in {"SendMessage", "message/send"}:
                return adapter.send_message_payload({**payload, "method": "message/send"})
            if method in {"GetTask", "tasks/get"}:
                params = _rpc_params(payload)
                task_id = _rpc_task_id(params)
                return _jsonrpc_success_payload(request_id, adapter.get_task(task_id))
            if method in {"CancelTask", "tasks/cancel"}:
                params = _rpc_params(payload)
                task_id = _rpc_task_id(params)
                reason = params.get("reason")
                if reason is not None and not isinstance(reason, str):
                    return _jsonrpc_protocol_error_response(
                        request_id,
                        code=-32602,
                        message="JSON-RPC params.reason must be a string.",
                    )
                return _jsonrpc_success_payload(request_id, adapter.cancel_task(task_id, reason=reason))
            if method in {"SendStreamingMessage", "message/stream"}:
                return _a2a_sse_response(_rpc_stream_message_events(adapter, payload))
            if method in {"SubscribeToTask", "tasks/subscribe"}:
                return _a2a_sse_response(_rpc_subscribe_task_events(adapter, payload, request))
            return _jsonrpc_protocol_error_response(
                request_id,
                code=-32601,
                message="JSON-RPC method not found.",
                local_code="method_not_found",
            )
        except ValueError as exc:
            return _jsonrpc_protocol_error_response(request_id, code=-32602, message=str(exc))
        except Exception as exc:
            return _jsonrpc_error_response(request_id, exc)

    @router.post("/message:send", response_model=None)
    def send_message(request: dict[str, Any]) -> dict[str, Any] | JSONResponse:
        try:
            return adapter.send_message_payload(request)
        except Exception as exc:
            if _is_jsonrpc_request(request):
                return _jsonrpc_error_response(request.get("id"), exc)
            raise _a2a_http_exception(exc) from exc

    @router.post("/message:stream")
    async def stream_message(request: dict[str, Any]) -> StreamingResponse:
        async def event_stream():
            try:
                result = await asyncio.to_thread(adapter.send_message_payload, request)
                yield _format_a2a_sse_event(result)
                task_id = _task_id_from_message_result(result)
                if task_id:
                    batch = await asyncio.to_thread(
                        adapter.wait_for_task_events,
                        task_id,
                        after_event_id=0,
                        timeout_seconds=0.0,
                    )
                    for event in batch.events:
                        yield _format_a2a_sse_event(event)
            except Exception as exc:
                if _is_jsonrpc_request(request):
                    yield _format_a2a_sse_event(_jsonrpc_error_payload(request.get("id"), exc))
                else:
                    error = error_info_from_exception(exc)
                    yield _format_a2a_sse_event(
                        {
                            "error": {
                                "code": error.code.value,
                                "message": error.public_message,
                            }
                        }
                    )

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        try:
            return _jsonrpc_success_payload(f"task-get-{task_id}", adapter.get_task(task_id))
        except Exception as exc:
            raise _a2a_http_exception(exc) from exc

    @router.post("/tasks/{task_id}:cancel", response_model=None)
    async def cancel_task(task_id: str, request: Request) -> dict[str, Any] | JSONResponse:
        cancel_request = await _parse_cancel_request(request, route_task_id=task_id)
        request_id = cancel_request.request_id if cancel_request.jsonrpc else f"cancel-{task_id}"
        if cancel_request.error is not None:
            if cancel_request.jsonrpc:
                return _jsonrpc_error_response(request_id, cancel_request.error)
            raise _a2a_http_exception(cancel_request.error)
        try:
            return _jsonrpc_success_payload(
                request_id,
                adapter.cancel_task(task_id, reason=cancel_request.reason),
            )
        except Exception as exc:
            if cancel_request.jsonrpc:
                return _jsonrpc_error_response(request_id, exc)
            raise _a2a_http_exception(exc) from exc

    @router.post("/tasks/{task_id}:subscribe")
    async def subscribe_task_events(
        task_id: str,
        request: Request,
        after: int = Query(default=0, ge=0),
    ) -> StreamingResponse:
        subscribe_request = await _parse_subscribe_request(request, route_task_id=task_id, query_after=after)
        if subscribe_request.error is None and not subscribe_request.jsonrpc:
            try:
                adapter.get_task(task_id)
            except Exception as exc:
                raise _a2a_http_exception(exc) from exc

        async def event_stream():
            if subscribe_request.error is not None:
                yield _format_a2a_sse_event(subscribe_request.error)
                return
            try:
                adapter.get_task(task_id)
            except Exception as exc:
                if subscribe_request.jsonrpc:
                    yield _format_a2a_sse_event(_jsonrpc_error_payload(subscribe_request.request_id, exc))
                    return
                raise

            last_event_id = subscribe_request.after_event_id
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
                state = _task_state(task)
                if _is_terminal_state(state):
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


def _a2a_sse_response(event_stream: Any) -> StreamingResponse:
    return StreamingResponse(
        event_stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _rpc_stream_message_events(adapter: A2AAdapter, payload: dict[str, Any]):
    request_id = payload.get("id")
    try:
        result = await asyncio.to_thread(adapter.send_message_payload, {**payload, "method": "message/send"})
        yield _format_a2a_sse_event(result)
        task_id = _task_id_from_message_result(result)
        if task_id:
            batch = await asyncio.to_thread(
                adapter.wait_for_task_events,
                task_id,
                after_event_id=0,
                timeout_seconds=0.0,
            )
            for event in batch.events:
                yield _format_a2a_sse_event(_jsonrpc_success_payload(request_id, event))
    except Exception as exc:
        yield _format_a2a_sse_event(_jsonrpc_error_payload(request_id, exc))


async def _rpc_subscribe_task_events(adapter: A2AAdapter, payload: dict[str, Any], request: Request):
    request_id = payload.get("id")
    try:
        params = _rpc_params(payload)
        task_id = _rpc_task_id(params)
        after_event_id = _rpc_after_event_id(params)
        adapter.get_task(task_id)
    except Exception as exc:
        yield _format_a2a_sse_event(_jsonrpc_error_payload(request_id, exc))
        return

    last_event_id = after_event_id
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
            yield _format_a2a_sse_event(_jsonrpc_success_payload(request_id, event))
        task = adapter.get_task(task_id)
        state = _task_state(task)
        if _is_terminal_state(state):
            trailing_batch = await asyncio.to_thread(
                adapter.wait_for_task_events,
                task_id,
                after_event_id=last_event_id,
                timeout_seconds=0.0,
            )
            last_event_id = max(last_event_id, trailing_batch.last_event_id)
            for event in trailing_batch.events:
                yield _format_a2a_sse_event(_jsonrpc_success_payload(request_id, event))
            break


class _SubscribeRequest:
    def __init__(
        self,
        *,
        request_id: Any = None,
        after_event_id: int = 0,
        error: dict[str, Any] | None = None,
        jsonrpc: bool = False,
    ) -> None:
        self.request_id = request_id
        self.after_event_id = after_event_id
        self.error = error
        self.jsonrpc = jsonrpc


class _CancelRequest:
    def __init__(
        self,
        *,
        request_id: Any = None,
        reason: str | None = None,
        error: Exception | None = None,
        jsonrpc: bool = False,
    ) -> None:
        self.request_id = request_id
        self.reason = reason
        self.error = error
        self.jsonrpc = jsonrpc


class _RpcRequest:
    def __init__(self, *, payload: dict[str, Any] | None = None, error: JSONResponse | None = None) -> None:
        self.payload = payload
        self.error = error


async def _parse_rpc_request(request: Request) -> _RpcRequest:
    body = await request.body()
    if not body.strip():
        return _RpcRequest(
            error=_jsonrpc_protocol_error_response(
                None,
                code=-32600,
                message="JSON-RPC request body is required.",
            )
        )
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return _RpcRequest(
            error=_jsonrpc_protocol_error_response(
                None,
                code=-32700,
                message="JSON parse error.",
                local_code="parse_error",
            )
        )
    if isinstance(payload, list):
        return _RpcRequest(
            error=_jsonrpc_protocol_error_response(
                None,
                code=-32600,
                message="JSON-RPC batch requests are not supported yet.",
                local_code="batch_not_supported",
            )
        )
    if not isinstance(payload, dict):
        return _RpcRequest(
            error=_jsonrpc_protocol_error_response(
                None,
                code=-32600,
                message="JSON-RPC request must be an object.",
            )
        )

    request_id = payload.get("id")
    if payload.get("jsonrpc") != "2.0":
        return _RpcRequest(
            error=_jsonrpc_protocol_error_response(
                request_id,
                code=-32600,
                message="JSON-RPC request jsonrpc must be '2.0'.",
            )
        )
    method = payload.get("method")
    if not isinstance(method, str) or not method:
        return _RpcRequest(
            error=_jsonrpc_protocol_error_response(
                request_id,
                code=-32600,
                message="JSON-RPC request method must be a string.",
            )
        )
    return _RpcRequest(payload=payload)


async def _parse_cancel_request(
    request: Request,
    *,
    route_task_id: str,
) -> _CancelRequest:
    body = await request.body()
    if not body.strip():
        return _CancelRequest()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        return _CancelRequest(jsonrpc=True, error=exc)
    if not isinstance(payload, dict):
        return _CancelRequest(jsonrpc=True, error=ValueError("JSON-RPC request must be an object."))

    if not _is_jsonrpc_request(payload) and "params" not in payload:
        reason = payload.get("reason")
        if reason is not None and not isinstance(reason, str):
            return _CancelRequest(error=ValueError("cancel reason must be a string."))
        return _CancelRequest(reason=reason)

    request_id = payload.get("id")
    if payload.get("jsonrpc") != "2.0":
        return _CancelRequest(
            jsonrpc=True,
            request_id=request_id,
            error=ValueError("JSON-RPC request jsonrpc must be '2.0'."),
        )
    if payload.get("method") not in {None, "tasks/cancel"}:
        return _CancelRequest(
            jsonrpc=True,
            request_id=request_id,
            error=ValueError("JSON-RPC method must be 'tasks/cancel'."),
        )
    params = payload.get("params") or {}
    if not isinstance(params, dict):
        return _CancelRequest(
            jsonrpc=True,
            request_id=request_id,
            error=ValueError("JSON-RPC params must be an object."),
        )
    param_task_id = params.get("id")
    if param_task_id is not None and param_task_id != route_task_id:
        return _CancelRequest(
            jsonrpc=True,
            request_id=request_id,
            error=ValueError("JSON-RPC params.id must match the route task id."),
        )
    reason = params.get("reason")
    if reason is not None and not isinstance(reason, str):
        return _CancelRequest(
            jsonrpc=True,
            request_id=request_id,
            error=ValueError("JSON-RPC params.reason must be a string."),
        )
    return _CancelRequest(jsonrpc=True, request_id=request_id, reason=reason)


async def _parse_subscribe_request(
    request: Request,
    *,
    route_task_id: str,
    query_after: int,
) -> _SubscribeRequest:
    body = await request.body()
    if not body.strip():
        return _SubscribeRequest(after_event_id=query_after)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        return _SubscribeRequest(jsonrpc=True, error=_jsonrpc_error_payload(None, exc))
    if not isinstance(payload, dict):
        return _SubscribeRequest(
            jsonrpc=True,
            error=_jsonrpc_error_payload(None, ValueError("JSON-RPC request must be an object.")),
        )

    request_id = payload.get("id")
    if payload.get("jsonrpc") != "2.0":
        return _SubscribeRequest(
            jsonrpc=True,
            request_id=request_id,
            error=_jsonrpc_error_payload(request_id, ValueError("JSON-RPC request jsonrpc must be '2.0'.")),
        )
    if payload.get("method") not in {None, "tasks/subscribe"}:
        return _SubscribeRequest(
            jsonrpc=True,
            request_id=request_id,
            error=_jsonrpc_error_payload(request_id, ValueError("JSON-RPC method must be 'tasks/subscribe'.")),
        )
    params = payload.get("params") or {}
    if not isinstance(params, dict):
        return _SubscribeRequest(
            jsonrpc=True,
            request_id=request_id,
            error=_jsonrpc_error_payload(request_id, ValueError("JSON-RPC params must be an object.")),
        )
    param_task_id = params.get("id")
    if param_task_id is not None and param_task_id != route_task_id:
        return _SubscribeRequest(
            jsonrpc=True,
            request_id=request_id,
            error=_jsonrpc_error_payload(
                request_id,
                ValueError("JSON-RPC params.id must match the route task id."),
            ),
        )
    after_event_id = params.get("afterEventId", query_after)
    if not isinstance(after_event_id, int) or after_event_id < 0:
        return _SubscribeRequest(
            jsonrpc=True,
            request_id=request_id,
            error=_jsonrpc_error_payload(
                request_id,
                ValueError("JSON-RPC params.afterEventId must be a non-negative integer."),
            ),
        )
    return _SubscribeRequest(jsonrpc=True, request_id=request_id, after_event_id=after_event_id)


def _a2a_http_exception(exc: Exception) -> HTTPException:
    error = error_info_from_exception(exc)
    return HTTPException(
        status_code=error.http_status,
        detail={
            "code": error.code.value,
            "message": error.public_message,
        },
    )


def _jsonrpc_error_response(request_id: Any, exc: Exception) -> JSONResponse:
    error_payload = _jsonrpc_error_payload(request_id, exc)
    error = error_info_from_exception(exc)
    return JSONResponse(status_code=error.http_status, content=error_payload)


def _jsonrpc_success_payload(request_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("jsonrpc") == "2.0" and ("result" in payload or "error" in payload):
        return {**payload, "id": request_id}
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": payload,
    }


def _jsonrpc_error_payload(request_id: Any, exc: Exception) -> dict[str, Any]:
    error = error_info_from_exception(exc)
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": _jsonrpc_error_code(error.code),
            "message": error.public_message,
            "data": _jsonrpc_error_data(error.code.value),
        },
    }


def _jsonrpc_protocol_error_response(
    request_id: Any,
    *,
    code: int,
    message: str,
    local_code: str = "invalid_request",
) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message,
                "data": _jsonrpc_error_data(local_code),
            },
        },
    )


def _jsonrpc_error_data(local_code: str) -> dict[str, Any]:
    return {
        "localCode": local_code,
        "errorInfo": {
            "reason": local_code,
            "domain": "vermay-agent",
            "metadata": {
                "localCode": local_code,
            },
        },
    }


def _rpc_params(payload: dict[str, Any]) -> dict[str, Any]:
    params = payload.get("params")
    if params is None:
        return {}
    if not isinstance(params, dict):
        raise ValueError("JSON-RPC params must be an object.")
    return params


def _rpc_task_id(params: dict[str, Any]) -> str:
    task_id = params.get("id", params.get("taskId"))
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("JSON-RPC params.id must be a non-empty string.")
    return task_id


def _rpc_after_event_id(params: dict[str, Any]) -> int:
    after_event_id = params.get("afterEventId", 0)
    if not isinstance(after_event_id, int) or after_event_id < 0:
        raise ValueError("JSON-RPC params.afterEventId must be a non-negative integer.")
    return after_event_id


def _jsonrpc_error_code(code: AgentErrorCode) -> int:
    if code == AgentErrorCode.INVALID_REQUEST:
        return -32602
    if code in {AgentErrorCode.SESSION_NOT_FOUND, AgentErrorCode.TASK_NOT_FOUND, AgentErrorCode.ARTIFACT_NOT_FOUND}:
        return -32004
    if code == AgentErrorCode.INVALID_SESSION_STATE:
        return -32009
    if code == AgentErrorCode.PERMISSION_ERROR:
        return -32003
    return -32000


def _is_jsonrpc_request(payload: dict[str, Any]) -> bool:
    return payload.get("jsonrpc") == "2.0" or payload.get("method") is not None


def _format_a2a_sse_event(event: dict[str, Any]) -> str:
    event_type = _sse_event_type(event)
    event_id = _event_id(event)
    data = json.dumps(event, ensure_ascii=False, sort_keys=True)
    prefix = f"id: {event_id}\n" if event_id is not None else ""
    return f"{prefix}event: {event_type}\ndata: {data}\n\n"


def _event_id(event: dict[str, Any]) -> int | None:
    if event.get("jsonrpc") == "2.0":
        result = event.get("result")
        if isinstance(result, dict):
            metadata = result.get("metadata")
            if isinstance(metadata, dict) and isinstance(metadata.get("localEventId"), int):
                return metadata["localEventId"]
    metadata = event.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("localEventId"), int):
        return metadata["localEventId"]
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


def _sse_event_type(event: dict[str, Any]) -> str:
    if event.get("jsonrpc") == "2.0":
        if isinstance(event.get("error"), dict):
            return "error"
        result = event.get("result")
        if isinstance(result, dict) and isinstance(result.get("kind"), str):
            return result["kind"]
    if isinstance(event.get("kind"), str):
        return event["kind"]
    return next(iter(event))


def _task_id_from_message_result(event: dict[str, Any]) -> str | None:
    if event.get("jsonrpc") == "2.0":
        result = event.get("result")
        if isinstance(result, dict) and result.get("kind") == "task" and isinstance(result.get("id"), str):
            return result["id"]
        return None
    if event.get("kind") == "task" and isinstance(event.get("id"), str):
        return event["id"]
    return None


def _task_state(task: dict[str, Any]) -> Any:
    if task.get("jsonrpc") == "2.0":
        result = task.get("result")
        if isinstance(result, dict):
            return result.get("status", {}).get("state")
    if task.get("kind") == "task":
        status = task.get("status")
        if isinstance(status, dict):
            return status.get("state")
    return None


def _is_terminal_state(state: Any) -> bool:
    if is_terminal_a2a_state(state):
        return True
    return state in {"completed", "failed", "canceled", "rejected"}
