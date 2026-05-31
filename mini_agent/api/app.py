from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from mini_agent.app_factory import DEFAULT_AGENT_STORE_PATH, RuntimeFactoryConfig
from mini_agent.langgraph_runtime import ModelProviderConfig
from mini_agent.storage import AgentStore

from .service import AgentService, AgentStartOptions
from .session_store import SessionStore


class ModelConfigRequest(BaseModel):
    provider: str = "ollama"
    options: dict[str, Any] = Field(default_factory=dict)


class SessionStartRequest(BaseModel):
    input: str = Field(min_length=1)
    thread_id: str | None = None
    max_loops: int | None = Field(default=None, gt=0)
    model: ModelConfigRequest | None = None


class ApprovalResumeRequest(BaseModel):
    approved: bool
    reason: str | None = None


def create_app(service: AgentService | None = None) -> FastAPI:
    owned_store = None
    owned_service = service
    if owned_service is None:
        owned_store = AgentStore(DEFAULT_AGENT_STORE_PATH)
        owned_service = AgentService(
            session_store=SessionStore(owned_store),
            default_config=RuntimeFactoryConfig(show_progress=False),
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            owned_service.close()
            if owned_store is not None:
                owned_store.close()

    app = FastAPI(title="Mini Agent Workbench API", version="0.1.0", lifespan=lifespan)
    app.state.agent_service = owned_service

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/sessions")
    def start_session(request: SessionStartRequest) -> dict[str, Any]:
        result = app.state.agent_service.start(
            request.input,
            thread_id=request.thread_id,
            options=AgentStartOptions(
                model=_model_config(request.model),
                max_loops=request.max_loops,
            ),
        )
        return result.to_dict()

    @app.get("/sessions/{thread_id}")
    def get_session(thread_id: str) -> dict[str, Any]:
        record = app.state.agent_service.get_session(thread_id)
        if record is None:
            raise HTTPException(status_code=404, detail="session not found")
        return record.to_dict()

    @app.post("/sessions/{thread_id}/resume")
    def resume_session(thread_id: str, request: ApprovalResumeRequest) -> dict[str, Any]:
        try:
            result = app.state.agent_service.resume(
                thread_id,
                approved=request.approved,
                reason=request.reason,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="session not found") from exc
        return result.to_dict()

    return app


def _model_config(request: ModelConfigRequest | None) -> ModelProviderConfig | None:
    if request is None:
        return None
    return ModelProviderConfig(provider=request.provider, options=request.options)
