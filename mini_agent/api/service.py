from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

from mini_agent.app_factory import RuntimeFactoryConfig, build_runtime
from mini_agent.langgraph_runtime import LangGraphAgentRuntime, ModelProviderConfig
from mini_agent.langgraph_runtime.results import RunResult

from .session_store import SessionRecord, SessionStore


RuntimeBuilder = Callable[[RuntimeFactoryConfig], LangGraphAgentRuntime]


@dataclass(frozen=True)
class AgentStartOptions:
    model: ModelProviderConfig | None = None
    max_loops: int | None = None


class AgentService:
    def __init__(
        self,
        *,
        session_store: SessionStore,
        default_config: RuntimeFactoryConfig | None = None,
        runtime_builder: RuntimeBuilder = build_runtime,
    ) -> None:
        self.session_store = session_store
        self.default_config = default_config or RuntimeFactoryConfig(show_progress=False)
        self.runtime_builder = runtime_builder
        self._default_runtime = runtime_builder(self.default_config)
        self._default_runtime_lock = threading.RLock()

    def start(
        self,
        user_input: str,
        *,
        thread_id: str | None = None,
        options: AgentStartOptions | None = None,
    ) -> RunResult:
        active_options = options or AgentStartOptions()
        runtime = self._runtime_for(active_options)
        try:
            if runtime is self._default_runtime:
                with self._default_runtime_lock:
                    result = runtime.start(user_input, thread_id=thread_id)
            else:
                result = runtime.start(user_input, thread_id=thread_id)
            self.session_store.save_result(
                user_input=user_input,
                result=result,
                model=_model_payload(active_options.model),
                max_loops=active_options.max_loops,
            )
            return result
        finally:
            if runtime is not self._default_runtime:
                runtime.close()

    def resume(self, thread_id: str, *, approved: bool, reason: str | None = None) -> RunResult:
        record = self.session_store.get(thread_id)
        if record is None:
            raise KeyError(f"unknown session: {thread_id}")
        options = _options_from_record(record)
        runtime = self._runtime_for(options)
        try:
            if runtime is self._default_runtime:
                with self._default_runtime_lock:
                    result = runtime.resume(thread_id=thread_id, approved=approved, reason=reason)
            else:
                result = runtime.resume(thread_id=thread_id, approved=approved, reason=reason)
            self.session_store.save_result(
                user_input=record.input,
                result=result,
                model=record.model,
                max_loops=record.max_loops,
            )
            return result
        finally:
            if runtime is not self._default_runtime:
                runtime.close()

    def get_session(self, thread_id: str) -> SessionRecord | None:
        return self.session_store.get(thread_id)

    def close(self) -> None:
        self._default_runtime.close()

    def _runtime_for(self, options: AgentStartOptions) -> LangGraphAgentRuntime:
        if options.model is None and options.max_loops is None:
            return self._default_runtime
        config = RuntimeFactoryConfig(
            model=options.model or self.default_config.model,
            max_loops=options.max_loops or self.default_config.max_loops,
            show_progress=False,
            trace_path=self.default_config.trace_path,
            checkpoint_path=self.default_config.checkpoint_path,
            agent_store_path=self.default_config.agent_store_path,
            skills_path=self.default_config.skills_path,
            skill_proposals_path=self.default_config.skill_proposals_path,
            mcp_config_path=self.default_config.mcp_config_path,
        )
        return self.runtime_builder(config)


def _model_payload(model: ModelProviderConfig | None) -> dict | None:
    if model is None:
        return None
    return {"provider": model.provider, "options": dict(model.options)}


def _options_from_record(record: SessionRecord) -> AgentStartOptions:
    model = None
    if record.model is not None:
        model = ModelProviderConfig(
            provider=str(record.model.get("provider") or "ollama"),
            options=dict(record.model.get("options") or {}),
        )
    return AgentStartOptions(model=model, max_loops=record.max_loops)
