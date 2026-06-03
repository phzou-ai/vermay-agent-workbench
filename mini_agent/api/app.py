from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from mini_agent.app_factory import DEFAULT_AGENT_STORE_PATH, DEFAULT_MODEL_CONFIG_PATH, RuntimeFactoryConfig
from mini_agent.errors import SessionNotFoundError, TaskNotFoundError, error_info_from_exception
from mini_agent.langgraph_runtime import ModelProviderConfig
from mini_agent.mcp_selection import MCPSelectionConfig
from mini_agent.model_selection import resolve_model_selection
from mini_agent.storage import AgentStore
from mini_agent.trace import TraceLogger

from .a2a import A2AAdapter, A2AAdapterConfig, A2AAgentCardConfig, create_a2a_router
from .lifecycle import TraceLifecycleObserver
from .service import AgentService, AgentStartOptions
from .session_models import is_terminal
from .session_store import SessionStore


class AgentErrorResponse(BaseModel):
    code: str
    message: str


class SessionCreateRequest(BaseModel):
    session_id: str | None = None
    context_id: str | None = None
    title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    session_id: str
    context_id: str | None = None
    title: str | None = None
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class TaskResponse(BaseModel):
    task_id: str
    session_id: str
    thread_id: str
    root_task_id: str | None = None
    retry_of_task_id: str | None = None
    status: str
    input: str
    attempt: int
    final_answer: str | None = None
    interrupt: Any | None = None
    interrupt_message: str | None = None
    stop_message: str | None = None
    error: AgentErrorResponse | None = None
    model: dict[str, Any] | None = None
    max_loops: int | None = None
    mcp: dict[str, Any] | None = None
    created_at: str
    updated_at: str


class TaskEventResponse(BaseModel):
    event_id: int
    task_id: str
    session_id: str
    context_id: str | None = None
    thread_id: str | None = None
    event_type: str
    status: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ModelConfigRequest(BaseModel):
    provider: str = "ollama"
    options: dict[str, Any] = Field(default_factory=dict)


class MCPPromptSelectionRequest(BaseModel):
    server: str = Field(min_length=1)
    name: str = Field(min_length=1)
    arguments: dict[str, str] = Field(default_factory=dict)


class MCPResourceSelectionRequest(BaseModel):
    server: str = Field(min_length=1)
    uri: str = Field(min_length=1)


class MCPSessionRequest(BaseModel):
    servers: list[str] = Field(default_factory=list)
    prompts: list[MCPPromptSelectionRequest] = Field(default_factory=list)
    resources: list[MCPResourceSelectionRequest] = Field(default_factory=list)


class TaskStartRequest(BaseModel):
    input: str = Field(min_length=1)
    task_id: str | None = None
    max_loops: int | None = Field(default=None, gt=0)
    model: str | ModelConfigRequest | None = None
    mcp: MCPSessionRequest | None = None
    wait: bool = True


class ApprovalResumeRequest(BaseModel):
    approved: bool
    reason: str | None = None
    wait: bool = True


class TaskCancelRequest(BaseModel):
    reason: str | None = None


class TaskRetryRequest(BaseModel):
    task_id: str | None = None
    reason: str | None = None
    wait: bool = True


def create_app(service: AgentService | None = None, *, enable_a2a: bool = False) -> FastAPI:
    owned_store = None
    owned_service = service
    owns_service = owned_service is None
    if owned_service is None:
        owned_store = AgentStore(DEFAULT_AGENT_STORE_PATH)
        default_config = RuntimeFactoryConfig(show_progress=False)
        owned_service = AgentService(
            session_store=SessionStore(owned_store),
            default_config=default_config,
            lifecycle_observer=TraceLifecycleObserver(TraceLogger(default_config.trace_path)),
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            if owns_service:
                owned_service.close()
            if owned_store is not None:
                owned_store.close()

    app = FastAPI(title="Mini Agent Workbench API", version="0.1.0", lifespan=lifespan)
    app.state.agent_service = owned_service
    if enable_a2a:
        app.include_router(
            create_a2a_router(
                A2AAdapter(
                    service=owned_service,
                    config=A2AAdapterConfig(agent_card=A2AAgentCardConfig(streaming=True)),
                )
            )
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    api_router = APIRouter(prefix="/api")

    @api_router.post("/sessions", response_model=SessionResponse)
    def create_session(request: SessionCreateRequest) -> dict[str, Any]:
        try:
            record = app.state.agent_service.create_session(
                session_id=request.session_id,
                context_id=request.context_id,
                title=request.title,
                metadata=request.metadata,
            )
            return record.to_dict()
        except Exception as exc:
            raise _http_exception(exc) from exc

    @api_router.get("/sessions", response_model=list[SessionResponse])
    def list_sessions() -> list[dict[str, Any]]:
        return [record.to_dict() for record in app.state.agent_service.list_sessions()]

    @api_router.get("/sessions/{session_id}", response_model=SessionResponse)
    def get_session(session_id: str) -> dict[str, Any]:
        record = app.state.agent_service.get_session(session_id)
        if record is None:
            raise _http_exception(SessionNotFoundError(session_id))
        return record.to_dict()

    @api_router.post("/sessions/{session_id}/tasks", response_model=TaskResponse)
    def start_task(session_id: str, request: TaskStartRequest) -> dict[str, Any]:
        try:
            record = app.state.agent_service.start_task(
                session_id,
                request.input,
                task_id=request.task_id,
                options=AgentStartOptions(
                    model=_model_config(request.model),
                    max_loops=request.max_loops,
                    mcp=_mcp_config(request.mcp),
                ),
                wait=request.wait,
            )
            return record.to_dict()
        except Exception as exc:
            raise _http_exception(exc) from exc

    @api_router.get("/tasks/{task_id}", response_model=TaskResponse)
    def get_task(task_id: str) -> dict[str, Any]:
        record = app.state.agent_service.get_task(task_id)
        if record is None:
            raise _http_exception(TaskNotFoundError(task_id))
        return record.to_dict()

    @api_router.get("/tasks/{task_id}/events", response_model=list[TaskEventResponse])
    def get_task_events(task_id: str) -> list[dict[str, Any]]:
        try:
            return [record.to_dict() for record in app.state.agent_service.list_task_events(task_id)]
        except Exception as exc:
            raise _http_exception(exc) from exc

    @api_router.get("/tasks/{task_id}/stream")
    async def stream_task_events(
        task_id: str,
        request: Request,
        after: int = Query(default=0, ge=0),
    ) -> StreamingResponse:
        if app.state.agent_service.get_task(task_id) is None:
            raise _http_exception(TaskNotFoundError(task_id))

        async def event_stream():
            last_event_id = after
            while True:
                if await request.is_disconnected():
                    break
                try:
                    events = await asyncio.to_thread(
                        app.state.agent_service.wait_for_task_events,
                        task_id,
                        after_event_id=last_event_id,
                        timeout_seconds=1.0,
                    )
                except Exception:
                    break
                for event in events:
                    last_event_id = max(last_event_id, event.event_id)
                    yield _format_sse_event(event.to_dict())

                task = app.state.agent_service.get_task(task_id)
                if task is None or is_terminal(task.status):
                    trailing_events = await asyncio.to_thread(
                        app.state.agent_service.wait_for_task_events,
                        task_id,
                        after_event_id=last_event_id,
                        timeout_seconds=0.0,
                    )
                    for event in trailing_events:
                        last_event_id = max(last_event_id, event.event_id)
                        yield _format_sse_event(event.to_dict())
                    break

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @api_router.post("/tasks/{task_id}/resume", response_model=TaskResponse)
    def resume_task(task_id: str, request: ApprovalResumeRequest) -> dict[str, Any]:
        try:
            record = app.state.agent_service.resume_task(
                task_id,
                approved=request.approved,
                reason=request.reason,
                wait=request.wait,
            )
            return record.to_dict()
        except Exception as exc:
            raise _http_exception(exc) from exc

    @api_router.post("/tasks/{task_id}/cancel", response_model=TaskResponse)
    def cancel_task(task_id: str, request: TaskCancelRequest | None = None) -> dict[str, Any]:
        try:
            record = app.state.agent_service.cancel_task(
                task_id,
                reason=request.reason if request is not None else None,
            )
            return record.to_dict()
        except Exception as exc:
            raise _http_exception(exc) from exc

    @api_router.post("/tasks/{task_id}/retry", response_model=TaskResponse)
    def retry_task(task_id: str, request: TaskRetryRequest | None = None) -> dict[str, Any]:
        try:
            record = app.state.agent_service.retry_task(
                task_id,
                new_task_id=request.task_id if request is not None else None,
                reason=request.reason if request is not None else None,
                wait=request.wait if request is not None else True,
            )
            return record.to_dict()
        except Exception as exc:
            raise _http_exception(exc) from exc

    app.include_router(api_router)

    return app


def _model_config(request: str | ModelConfigRequest | None) -> ModelProviderConfig | None:
    if isinstance(request, str):
        return resolve_model_selection(
            config_path=DEFAULT_MODEL_CONFIG_PATH,
            model_name=request,
        )
    if request is None:
        return None
    return ModelProviderConfig(provider=request.provider, options=request.options)


def _mcp_config(request: MCPSessionRequest | None) -> MCPSelectionConfig | None:
    if request is None:
        return None
    payload = request.model_dump() if hasattr(request, "model_dump") else request.dict()
    return MCPSelectionConfig.from_payload(payload)


def _http_exception(exc: Exception) -> HTTPException:
    error = error_info_from_exception(exc)
    return HTTPException(status_code=error.http_status, detail=error.public_message)


def _format_sse_event(event: dict[str, Any]) -> str:
    event_id = event["event_id"]
    event_type = event["event_type"]
    data = json.dumps(event, ensure_ascii=False, sort_keys=True)
    return f"id: {event_id}\nevent: {event_type}\ndata: {data}\n\n"
