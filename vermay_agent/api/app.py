from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from vermay_agent.app_factory import DEFAULT_AGENT_STORE_PATH, DEFAULT_MODEL_CONFIG_PATH, RuntimeFactoryConfig, build_runtime
from vermay_agent.errors import error_info_from_exception
from vermay_agent.langgraph_runtime import build_model_client
from vermay_agent.main_agent import (
    DevMockLocalMessageResponder,
    DevMockLocalTaskRunner,
    DirectA2ARemoteAgentClient,
    DirectLangGraphLocalTaskRunner,
    DirectModelLocalMessageResponder,
    DirectModelRouterModelClient,
    DefaultMainAgentRouter,
    MainAgentCore,
    MainAgentStore,
    build_dev_mock_runtime,
    fetch_agent_card,
)
from vermay_agent.model_selection import resolve_model_selection
from vermay_agent.storage import AgentStore
from vermay_agent.trace import TraceLogger

from .a2a import A2AAdapter, A2AAdapterConfig, A2AAgentCardConfig, create_a2a_router
from .lifecycle import TraceLifecycleObserver
from .service import AgentService
from .session_store import SessionStore


class RegisteredAgentUpsertRequest(BaseModel):
    agent_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    card_url: str = Field(min_length=1)
    card_json: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class RegisteredAgentResponse(BaseModel):
    agent_id: str
    name: str
    card_url: str
    card_json: dict[str, Any] = Field(default_factory=dict)
    enabled: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


def create_app(
    service: AgentService | None = None,
    *,
    enable_a2a: bool = False,
    main_agent_core: MainAgentCore | None = None,
    dev_mock_main_agent: bool | None = None,
) -> FastAPI:
    owned_store = None
    owned_service = service
    owned_task_runner = None
    owns_service = owned_service is None
    use_dev_mock_main_agent = _dev_mock_main_agent_enabled(dev_mock_main_agent)
    if owned_service is None:
        owned_store = AgentStore(DEFAULT_AGENT_STORE_PATH)
        default_config = RuntimeFactoryConfig(show_progress=False)
        owned_service = AgentService(
            session_store=SessionStore(owned_store),
            default_config=default_config,
            runtime_builder=build_dev_mock_runtime if use_dev_mock_main_agent else build_runtime,
            lifecycle_observer=TraceLifecycleObserver(TraceLogger(default_config.trace_path)),
        )
        if main_agent_core is None:
            if use_dev_mock_main_agent:
                local_message_responder = DevMockLocalMessageResponder()
                owned_task_runner = DevMockLocalTaskRunner()
            else:
                active_model = resolve_model_selection(config_path=DEFAULT_MODEL_CONFIG_PATH)
                local_message_responder = DirectModelLocalMessageResponder(build_model_client(active_model))
                owned_task_runner = DirectLangGraphLocalTaskRunner(build_runtime(default_config))
            router = None
            router_model_name = _router_model_name()
            if router_model_name and not use_dev_mock_main_agent:
                router_model_config = resolve_model_selection(
                    config_path=DEFAULT_MODEL_CONFIG_PATH,
                    model_name=router_model_name,
                )
                router = DefaultMainAgentRouter(
                    router_model=DirectModelRouterModelClient(
                        build_model_client(router_model_config),
                        model_name=router_model_name,
                    )
                )
            main_agent_core = MainAgentCore(
                store=MainAgentStore(owned_store),
                local_message_responder=local_message_responder,
                local_task_runner=owned_task_runner,
                remote_agent_client=DirectA2ARemoteAgentClient(),
                router=router,
            )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            if owned_task_runner is not None:
                owned_task_runner.close()
            if owns_service:
                owned_service.close()
            if owned_store is not None:
                owned_store.close()

    app = FastAPI(title="Vermay Agent Workbench API", version="0.1.0", lifespan=lifespan)
    app.state.agent_service = owned_service
    app.state.main_agent_core = main_agent_core

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        if request.url.path.startswith("/api/") and _is_error_payload(exc.detail):
            return JSONResponse(status_code=exc.status_code, content=exc.detail, headers=exc.headers)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)

    if enable_a2a:
        app.include_router(
            create_a2a_router(
                A2AAdapter(
                    service=owned_service,
                    config=A2AAdapterConfig(agent_card=A2AAgentCardConfig(streaming=True)),
                    main_agent_core=main_agent_core,
                )
            )
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    api_router = APIRouter(prefix="/api")

    @api_router.get("/contexts")
    def list_contexts() -> list[dict[str, Any]]:
        core = _main_agent_core(app)
        return [_context_to_dict(record) for record in core.store.list_contexts()]

    @api_router.get("/contexts/{context_id}")
    def get_context(context_id: str) -> dict[str, Any]:
        core = _main_agent_core(app)
        record = core.store.get_context(context_id)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "context_not_found", "message": "context not found"})
        return _context_to_dict(record)

    @api_router.get("/contexts/{context_id}/messages")
    def list_context_messages(context_id: str, limit: int | None = Query(default=None, ge=1)) -> list[dict[str, Any]]:
        core = _main_agent_core(app)
        if core.store.get_context(context_id) is None:
            raise HTTPException(status_code=404, detail={"code": "context_not_found", "message": "context not found"})
        return [_message_to_dict(record) for record in core.store.list_context_messages(context_id, limit=limit)]

    @api_router.get("/contexts/{context_id}/tasks")
    def list_context_tasks(context_id: str) -> list[dict[str, Any]]:
        core = _main_agent_core(app)
        if core.store.get_context(context_id) is None:
            raise HTTPException(status_code=404, detail={"code": "context_not_found", "message": "context not found"})
        return [_task_to_dict(record) for record in core.store.list_context_tasks(context_id)]

    @api_router.get("/contexts/{context_id}/route-decisions")
    def list_context_route_decisions(context_id: str) -> list[dict[str, Any]]:
        core = _main_agent_core(app)
        if core.store.get_context(context_id) is None:
            raise HTTPException(status_code=404, detail={"code": "context_not_found", "message": "context not found"})
        return [_route_decision_to_dict(record) for record in core.store.list_context_route_decisions(context_id)]

    @api_router.get("/contexts/{context_id}/delegations")
    def list_context_delegations(context_id: str) -> list[dict[str, Any]]:
        core = _main_agent_core(app)
        if core.store.get_context(context_id) is None:
            raise HTTPException(status_code=404, detail={"code": "context_not_found", "message": "context not found"})
        return [_delegation_to_dict(record) for record in core.store.list_context_delegations(context_id)]

    @api_router.delete("/contexts/{context_id}", status_code=204)
    def delete_context(context_id: str, force: bool = Query(default=False)) -> None:
        core = _main_agent_core(app)
        if core.store.get_context(context_id) is None:
            raise HTTPException(status_code=404, detail={"code": "context_not_found", "message": "context not found"})
        try:
            core.store.delete_context(context_id, force=force)
        except Exception as exc:
            raise _http_exception(exc) from exc

    @api_router.get("/registered-agents", response_model=list[RegisteredAgentResponse])
    def list_registered_agents(enabled_only: bool = Query(default=False)) -> list[dict[str, Any]]:
        core = _main_agent_core(app)
        return [
            _registered_agent_to_dict(record)
            for record in core.store.list_registered_agents(enabled_only=enabled_only)
        ]

    @api_router.post("/registered-agents", response_model=RegisteredAgentResponse)
    def upsert_registered_agent(request: RegisteredAgentUpsertRequest) -> dict[str, Any]:
        core = _main_agent_core(app)
        try:
            record = core.store.upsert_registered_agent(
                agent_id=request.agent_id,
                name=request.name,
                card_url=request.card_url,
                card_json=request.card_json,
                enabled=request.enabled,
                metadata=request.metadata,
            )
            return _registered_agent_to_dict(record)
        except Exception as exc:
            raise _http_exception(exc) from exc

    @api_router.get("/registered-agents/{agent_id}", response_model=RegisteredAgentResponse)
    def get_registered_agent(agent_id: str) -> dict[str, Any]:
        core = _main_agent_core(app)
        record = core.store.get_registered_agent(agent_id)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "registered_agent_not_found", "message": "registered agent not found"},
            )
        return _registered_agent_to_dict(record)

    @api_router.post("/registered-agents/{agent_id}/refresh-card", response_model=RegisteredAgentResponse)
    def refresh_registered_agent_card(agent_id: str) -> dict[str, Any]:
        core = _main_agent_core(app)
        record = core.store.get_registered_agent(agent_id)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "registered_agent_not_found", "message": "registered agent not found"},
            )
        try:
            card_json = fetch_agent_card(record.card_url)
            refreshed = core.store.update_registered_agent_card(agent_id, card_json=card_json)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "agent_card_refresh_failed", "message": str(exc)},
            ) from exc
        if refreshed is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "registered_agent_not_found", "message": "registered agent not found"},
            )
        return _registered_agent_to_dict(refreshed)

    @api_router.delete("/registered-agents/{agent_id}", status_code=204)
    def delete_registered_agent(agent_id: str) -> None:
        core = _main_agent_core(app)
        if not core.store.delete_registered_agent(agent_id):
            raise HTTPException(
                status_code=404,
                detail={"code": "registered_agent_not_found", "message": "registered agent not found"},
            )

    app.include_router(api_router)

    return app


def _dev_mock_main_agent_enabled(value: bool | None) -> bool:
    if value is not None:
        return value
    return _truthy_env(os.environ.get("VERMAY_AGENT_DEV_MOCK_MAIN_AGENT"))


def _router_model_name() -> str | None:
    value = os.environ.get("VERMAY_AGENT_ROUTER_MODEL")
    if value is None:
        return None
    value = value.strip()
    return value or None


def _truthy_env(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _http_exception(exc: Exception) -> HTTPException:
    error = error_info_from_exception(exc)
    return HTTPException(
        status_code=error.http_status,
        detail={
            "code": error.code.value,
            "message": error.public_message,
        },
    )


def _main_agent_core(app: FastAPI) -> MainAgentCore:
    core = getattr(app.state, "main_agent_core", None)
    if core is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "main agent core not enabled"})
    return core


def _context_to_dict(record) -> dict[str, Any]:
    return {
        "context_id": record.context_id,
        "title": record.title,
        "metadata": record.metadata,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _message_to_dict(record) -> dict[str, Any]:
    return {
        "message_id": record.message_id,
        "context_id": record.context_id,
        "role": record.role.value,
        "parts": record.parts,
        "task_id": record.task_id,
        "metadata": record.metadata,
        "created_at": record.created_at,
    }


def _task_to_dict(record) -> dict[str, Any]:
    return {
        "task_id": record.task_id,
        "context_id": record.context_id,
        "status": record.status.value,
        "input_message_id": record.input_message_id,
        "output_message_id": record.output_message_id,
        "runtime_thread_id": record.runtime_thread_id,
        "assigned_agent_id": record.assigned_agent_id,
        "retry_of_task_id": record.retry_of_task_id,
        "attempt": record.attempt,
        "model": record.model,
        "max_loops": record.max_loops,
        "mcp": record.mcp,
        "error_code": record.error_code,
        "error_message": record.error_message,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _route_decision_to_dict(record) -> dict[str, Any]:
    return {
        "decision_id": record.decision_id,
        "context_id": record.context_id,
        "message_id": record.message_id,
        "kind": record.kind.value,
        "reason": record.reason,
        "confidence": record.confidence,
        "target_agent_id": record.target_agent_id,
        "metadata": record.metadata,
        "created_at": record.created_at,
    }


def _delegation_to_dict(record) -> dict[str, Any]:
    return {
        "delegation_id": record.delegation_id,
        "context_id": record.context_id,
        "input_message_id": record.input_message_id,
        "route_decision_id": record.route_decision_id,
        "remote_agent_id": record.remote_agent_id,
        "local_task_id": record.local_task_id,
        "remote_task_id": record.remote_task_id,
        "remote_context_id": record.remote_context_id,
        "remote_message_id": record.remote_message_id,
        "result_kind": record.result_kind,
        "status": record.status,
        "metadata": record.metadata,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _registered_agent_to_dict(record) -> dict[str, Any]:
    return {
        "agent_id": record.agent_id,
        "name": record.name,
        "card_url": record.card_url,
        "card_json": record.card_json,
        "enabled": record.enabled,
        "metadata": record.metadata,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _is_error_payload(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("code"), str)
        and isinstance(value.get("message"), str)
    )
