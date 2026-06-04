from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from typing import Callable, Iterator

from vermay_agent.errors import InvalidSessionStateError


class TaskExecutionConflictError(InvalidSessionStateError):
    pass


class TaskExecutionService:
    def __init__(self, *, max_workers: int = 4) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="vermay-agent-task")

    def submit(self, func: Callable[..., None], *args: object) -> Future:
        return self._executor.submit(func, *args)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)


class TaskEventNotifier:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._latest_event_id_by_task: dict[str, int] = {}

    def notify(self, task_id: str, event_id: int) -> None:
        with self._condition:
            self._latest_event_id_by_task[task_id] = max(
                event_id,
                self._latest_event_id_by_task.get(task_id, 0),
            )
            self._condition.notify_all()

    def wait(self, task_id: str, *, after_event_id: int, timeout_seconds: float) -> None:
        with self._condition:
            self._condition.wait_for(
                lambda: self._latest_event_id_by_task.get(task_id, 0) > after_event_id,
                timeout=timeout_seconds,
            )


class TaskExecutionLocks:
    def __init__(self, *, conflict_error: type[Exception] = TaskExecutionConflictError) -> None:
        self._guard = threading.RLock()
        self._locks: dict[str, threading.Lock] = {}
        self._conflict_error = conflict_error

    @contextmanager
    def acquire(self, task_id: str, *, blocking: bool = False) -> Iterator[None]:
        lock = self._lock_for(task_id)
        acquired = lock.acquire(blocking=blocking)
        if not acquired:
            raise self._conflict_error(f"task is already running: {task_id}")
        try:
            yield
        finally:
            lock.release()
            self._prune_lock(task_id, lock)

    def _lock_for(self, task_id: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(task_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[task_id] = lock
            return lock

    def _prune_lock(self, task_id: str, lock: threading.Lock) -> None:
        with self._guard:
            if self._locks.get(task_id) is lock and not lock.locked():
                del self._locks[task_id]
