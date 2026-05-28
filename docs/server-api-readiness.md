# Server/API Readiness

## Scope

This document records the runtime boundary needed before adding a server or API layer.

No HTTP server is implemented in the current project. The active goal is to keep `LangGraphAgentRuntime` usable as a shared engine while external layers own session identity and UI state.

## Runtime Contract

The runtime exposes structured methods:

```python
start(user_input, thread_id=None, stream_modes=None) -> RunResult
resume(thread_id, approved, reason=None) -> RunResult
```

Compatibility methods remain available for CLI string output:

```python
run(...) -> str
resume_approval(...) -> str
```

Server or API code should use `start(...)` and `resume(...)`, not the string compatibility methods.

## Session Mapping

An API layer should map external session identifiers to LangGraph thread ids:

```text
HTTP session id / conversation id / user task id
  -> LangGraph thread_id
```

The runtime does not store active session state. The caller must pass `thread_id` explicitly when continuing or resuming a run.

## API Response Shape

`RunResult.to_dict()` provides a stable API-facing payload:

```json
{
  "thread_id": "session-a",
  "status": "interrupted",
  "final_answer": null,
  "interrupt": {},
  "interrupt_message": "Approval required...",
  "stop_message": null
}
```

Status values:

```text
completed
interrupted
stopped
unknown
```

The full graph state is excluded by default. Call `to_dict(include_state=True)` only for trusted debugging paths, not public API responses.

## Approval State

Approval prompts are UI/session state. A server should store pending approval metadata outside the runtime:

```text
session store:
  session_id
  thread_id
  pending interrupt message
  pending interrupt payload
  created_at / expires_at
```

Resume should call:

```python
runtime.resume(thread_id=thread_id, approved=True, reason="approved")
```

## Non-Goals

- Do not add a web server before the API contract is stable.
- Do not store active sessions on `LangGraphAgentRuntime`.
- Do not expose raw graph state by default.
- Do not treat `RunResult.interrupt_message` as the source of truth for resume. The source of truth remains `thread_id` plus the LangGraph checkpoint store.
