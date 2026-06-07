from __future__ import annotations

from uuid import uuid4

from .context import recent_messages
from .models import (
    LocalMessageResult,
    LocalTaskResult,
    MainAgentRequest,
    MainAgentResult,
    MessageRole,
    RemoteAgentResult,
    RouteDecisionKind,
    TaskStatus,
)
from .remote_agent import RemoteAgentClient
from .responder import LocalMessageResponder
from .router import DefaultMainAgentRouter, MainAgentRouteDecision, MainAgentRouter
from .store import MainAgentStore
from .task_runner import LocalTaskRunner


class MainAgentCore:
    def __init__(
        self,
        *,
        store: MainAgentStore,
        local_message_responder: LocalMessageResponder,
        local_task_runner: LocalTaskRunner | None = None,
        remote_agent_client: RemoteAgentClient | None = None,
        router: MainAgentRouter | None = None,
    ) -> None:
        self.store = store
        self.local_message_responder = local_message_responder
        self.local_task_runner = local_task_runner
        self.remote_agent_client = remote_agent_client
        self.router = router or DefaultMainAgentRouter()

    def handle_message(self, request: MainAgentRequest) -> MainAgentResult:
        if request.role != MessageRole.USER:
            raise ValueError("main agent request role must be user")
        context_id = self._resolve_context_id(request.context_id)
        message_id = request.message_id or _new_id("msg")
        user_message = self.store.append_message(
            message_id=message_id,
            context_id=context_id,
            role=request.role,
            parts=request.parts,
            metadata=request.metadata,
        )
        route_decision = self.router.decide(
            request=request,
            context_id=context_id,
            input_message_id=user_message.message_id,
            messages=recent_messages(self.store, context_id, limit=10),
            store=self.store,
        )
        if route_decision.kind == RouteDecisionKind.LOCAL_MESSAGE:
            return self._handle_local_message(
                context_id=context_id,
                input_message_id=user_message.message_id,
                route_decision=route_decision,
            )
        if route_decision.kind == RouteDecisionKind.LOCAL_TASK:
            return self._handle_local_task(
                context_id=context_id,
                input_message_id=user_message.message_id,
                route_decision=route_decision,
            )
        if route_decision.kind == RouteDecisionKind.REMOTE_AGENT:
            return self._handle_remote_agent(
                context_id=context_id,
                input_message_id=user_message.message_id,
                request=request,
                route_decision=route_decision,
            )
        raise ValueError(f"unsupported route decision: {route_decision.kind.value}")

    def _resolve_context_id(self, context_id: str | None) -> str:
        if context_id is None:
            context = self.store.create_context(context_id=_new_id("ctx"))
            return context.context_id
        if self.store.get_context(context_id) is None:
            raise ValueError(f"unknown context: {context_id}")
        return context_id

    def _handle_local_message(
        self,
        *,
        context_id: str,
        input_message_id: str,
        route_decision: MainAgentRouteDecision,
    ) -> LocalMessageResult:
        decision = self.store.record_route_decision(
            decision_id=_new_id("route"),
            context_id=context_id,
            message_id=input_message_id,
            kind=RouteDecisionKind.LOCAL_MESSAGE,
            reason=route_decision.reason,
            confidence=route_decision.confidence,
            metadata=route_decision.metadata,
        )
        parts = self.local_message_responder.respond(recent_messages(self.store, context_id, limit=10))
        assistant_message = self.store.append_message(
            message_id=_new_id("msg"),
            context_id=context_id,
            role=MessageRole.AGENT,
            parts=parts,
            metadata={
                "inputMessageId": input_message_id,
                "routeDecisionId": decision.decision_id,
                "routeKind": RouteDecisionKind.LOCAL_MESSAGE.value,
            },
        )
        return LocalMessageResult(
            kind=RouteDecisionKind.LOCAL_MESSAGE,
            context_id=context_id,
            message_id=assistant_message.message_id,
            input_message_id=input_message_id,
            route_decision_id=decision.decision_id,
            parts=assistant_message.parts,
        )

    def _handle_local_task(
        self,
        *,
        context_id: str,
        input_message_id: str,
        route_decision: MainAgentRouteDecision,
    ) -> LocalTaskResult:
        decision = self.store.record_route_decision(
            decision_id=_new_id("route"),
            context_id=context_id,
            message_id=input_message_id,
            kind=RouteDecisionKind.LOCAL_TASK,
            reason=route_decision.reason,
            confidence=route_decision.confidence,
            metadata=route_decision.metadata,
        )
        task = self.store.create_task(
            task_id=_new_id("task"),
            context_id=context_id,
            input_message_id=input_message_id,
            runtime_thread_id=_new_id("thread"),
            status=TaskStatus.CREATED,
        )
        self.store.append_task_event(task_id=task.task_id, type="task_created", status=TaskStatus.CREATED)
        if self.local_task_runner is not None:
            task = self._run_local_task(task.task_id, context_id=context_id, route_decision_id=decision.decision_id)
        return LocalTaskResult(
            kind=RouteDecisionKind.LOCAL_TASK,
            context_id=context_id,
            task_id=task.task_id,
            input_message_id=input_message_id,
            route_decision_id=decision.decision_id,
        )

    def _run_local_task(self, task_id: str, *, context_id: str, route_decision_id: str):
        task = self.store.update_task_status(task_id, TaskStatus.RUNNING)
        self.store.append_task_event(task_id=task_id, type="task_started", status=TaskStatus.RUNNING)
        try:
            result = self.local_task_runner.run(
                recent_messages(self.store, context_id, limit=10),
                thread_id=task.runtime_thread_id,
            )
        except Exception as exc:
            failed = self.store.update_task_status(
                task_id,
                TaskStatus.FAILED,
                error_code=exc.__class__.__name__,
                error_message=str(exc),
            )
            self.store.append_task_event(
                task_id=task_id,
                type="task_failed",
                status=TaskStatus.FAILED,
                payload={"error_code": failed.error_code, "error_message": failed.error_message},
            )
            return failed

        if result.status == TaskStatus.COMPLETED:
            assistant_message = self.store.append_message(
                message_id=_new_id("msg"),
                context_id=context_id,
                role=MessageRole.AGENT,
                parts=result.parts,
                task_id=task_id,
                metadata={
                    "routeDecisionId": route_decision_id,
                    "routeKind": RouteDecisionKind.LOCAL_TASK.value,
                },
            )
            artifact_parts = result.artifact_parts or result.parts
            artifact = self.store.upsert_artifact(
                artifact_id=f"{task_id}:final_answer",
                task_id=task_id,
                context_id=context_id,
                parts=artifact_parts,
                metadata={"kind": "final_answer", "outputMessageId": assistant_message.message_id},
            )
            self.store.append_task_event(
                task_id=task_id,
                type="task_artifact_created",
                status=TaskStatus.COMPLETED,
                payload={"artifact_id": artifact.artifact_id, "kind": "final_answer"},
            )
            task = self.store.set_task_output_message(task_id, assistant_message.message_id)
            task = self.store.update_task_status(task_id, TaskStatus.COMPLETED)
            self.store.append_task_event(task_id=task_id, type="task_completed", status=TaskStatus.COMPLETED)
            return task

        failed = self.store.update_task_status(
            task_id,
            TaskStatus.FAILED,
            error_code=result.error_code or "task_not_completed",
            error_message=result.error_message or f"local task ended with unsupported status: {result.status.value}",
        )
        self.store.append_task_event(
            task_id=task_id,
            type="task_failed",
            status=TaskStatus.FAILED,
            payload={"error_code": failed.error_code, "error_message": failed.error_message},
        )
        return failed

    def _handle_remote_agent(
        self,
        *,
        context_id: str,
        input_message_id: str,
        request: MainAgentRequest,
        route_decision: MainAgentRouteDecision,
    ) -> RemoteAgentResult:
        target_agent_id = route_decision.target_agent_id
        if target_agent_id is None:
            raise ValueError("remote_agent route requires metadata.targetAgentId")
        agent = self.store.get_registered_agent(target_agent_id)
        if agent is None:
            raise ValueError(f"unknown registered agent: {target_agent_id}")
        if not agent.enabled:
            raise ValueError(f"registered agent is disabled: {target_agent_id}")
        if self.remote_agent_client is None:
            raise ValueError("remote_agent client is not configured")

        decision = self.store.record_route_decision(
            decision_id=_new_id("route"),
            context_id=context_id,
            message_id=input_message_id,
            kind=RouteDecisionKind.REMOTE_AGENT,
            target_agent_id=target_agent_id,
            reason=route_decision.reason,
            confidence=route_decision.confidence,
            metadata=route_decision.metadata,
        )
        remote = self.remote_agent_client.send_message(
            agent=agent,
            request=request,
            context_id=context_id,
            message_id=input_message_id,
        )
        delegation_id = _new_id("delegate")

        if remote.kind == "message":
            assistant_message = self.store.append_message(
                message_id=_new_id("msg"),
                context_id=context_id,
                role=MessageRole.AGENT,
                parts=remote.parts,
                metadata={
                    "inputMessageId": input_message_id,
                    "routeDecisionId": decision.decision_id,
                    "routeKind": RouteDecisionKind.REMOTE_AGENT.value,
                    "remoteAgentId": target_agent_id,
                    "remoteContextId": remote.context_id,
                    "remoteMessageId": remote.message_id,
                },
            )
            self.store.create_delegated_task(
                delegation_id=delegation_id,
                context_id=context_id,
                input_message_id=input_message_id,
                route_decision_id=decision.decision_id,
                remote_agent_id=target_agent_id,
                remote_context_id=remote.context_id,
                remote_message_id=remote.message_id,
                result_kind="message",
                status="completed",
                metadata={"localMessageId": assistant_message.message_id},
            )
            return RemoteAgentResult(
                kind=RouteDecisionKind.REMOTE_AGENT,
                context_id=context_id,
                input_message_id=input_message_id,
                target_agent_id=target_agent_id,
                route_decision_id=decision.decision_id,
                delegation_id=delegation_id,
                message_id=assistant_message.message_id,
                parts=assistant_message.parts,
            )

        if remote.kind == "task":
            task = self.store.create_task(
                task_id=_new_id("task"),
                context_id=context_id,
                input_message_id=input_message_id,
                runtime_thread_id=_new_id("remote-thread"),
                assigned_agent_id=target_agent_id,
                status=_remote_task_status(remote.status),
            )
            self.store.append_task_event(
                task_id=task.task_id,
                type="task_delegated",
                status=task.status,
                payload={
                    "remote_agent_id": target_agent_id,
                    "remote_task_id": remote.task_id,
                    "remote_context_id": remote.context_id,
                },
            )
            self.store.create_delegated_task(
                delegation_id=delegation_id,
                context_id=context_id,
                input_message_id=input_message_id,
                route_decision_id=decision.decision_id,
                remote_agent_id=target_agent_id,
                local_task_id=task.task_id,
                remote_task_id=remote.task_id,
                remote_context_id=remote.context_id,
                result_kind="task",
                status=remote.status or task.status.value,
            )
            return RemoteAgentResult(
                kind=RouteDecisionKind.REMOTE_AGENT,
                context_id=context_id,
                input_message_id=input_message_id,
                target_agent_id=target_agent_id,
                route_decision_id=decision.decision_id,
                delegation_id=delegation_id,
                task_id=task.task_id,
            )

        raise ValueError(f"unsupported remote agent result kind: {remote.kind}")


def _remote_task_status(status: str | None) -> TaskStatus:
    if status in {"submitted", "TASK_STATE_SUBMITTED", "created", "queued"}:
        return TaskStatus.QUEUED
    if status in {"working", "TASK_STATE_WORKING", "running"}:
        return TaskStatus.RUNNING
    if status in {"completed", "TASK_STATE_COMPLETED"}:
        return TaskStatus.COMPLETED
    if status in {"canceled", "cancelled", "TASK_STATE_CANCELED"}:
        return TaskStatus.CANCELED
    if status in {"input-required", "TASK_STATE_INPUT_REQUIRED"}:
        return TaskStatus.INPUT_REQUIRED
    if status in {"auth-required", "TASK_STATE_AUTH_REQUIRED"}:
        return TaskStatus.AUTH_REQUIRED
    return TaskStatus.FAILED


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"
