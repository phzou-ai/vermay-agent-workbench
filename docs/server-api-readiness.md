# Server/API

## Current API Surface

The project includes a local FastAPI server for agent lifecycle operations.

Start the server:

```bash
vermay-agent serve
```

Default bind address:

```text
127.0.0.1:8000
```

Endpoints:

```text
GET  /health
POST /api/sessions
GET  /api/sessions
GET  /api/sessions/{session_id}
POST /api/sessions/{session_id}/tasks
GET  /api/tasks/{task_id}
GET  /api/tasks/{task_id}/events
GET  /api/tasks/{task_id}/stream
POST /api/tasks/{task_id}/resume
POST /api/tasks/{task_id}/cancel
POST /api/tasks/{task_id}/retry
```

The API is local-only and does not add authentication by default. Do not expose it beyond a trusted local environment without adding an access-control layer.

Local lifecycle endpoints use the `/api` prefix. A2A protocol routes, when enabled, remain at their protocol-defined root paths.

## Identity Model

The API separates conversation context from execution lifecycle:

```text
session_id
  long-lived conversation/context container

task_id
  single agent execution started by one user input

thread_id
  internal LangGraph checkpoint key
```

`thread_id` appears in task payloads for debugging and checkpoint correlation, but normal API operations use `session_id` and `task_id`.

## Create Session

`POST /api/sessions`

Request:

```json
{
  "session_id": "optional-client-session-id",
  "context_id": "optional-external-context-id",
  "title": "Ops session",
  "metadata": {
    "source": "local"
  }
}
```

Response:

```json
{
  "session_id": "session-a",
  "context_id": null,
  "title": "Ops session",
  "status": "active",
  "metadata": {},
  "created_at": "...",
  "updated_at": "..."
}
```

## Start Task

`POST /api/sessions/{session_id}/tasks`

Request:

```json
{
  "input": "check k8s status",
  "task_id": "optional-client-task-id",
  "max_loops": 5,
  "model": "local_ollama",
  "mcp": {
    "servers": ["k8s"]
  },
  "wait": true
}
```

Only `input` is required. When omitted, `task_id`, `max_loops`, `model`, and `mcp` use service/runtime defaults. `wait` defaults to `true`.

When `wait` is `false`, the request returns after the task is created and queued. The task continues in a background worker and can be inspected through `GET /api/tasks/{task_id}` and `GET /api/tasks/{task_id}/events`.

Response:

```json
{
  "task_id": "task-a",
  "session_id": "session-a",
  "thread_id": "task:task-a:attempt:1",
  "root_task_id": "task-a",
  "retry_of_task_id": null,
  "status": "completed",
  "input": "check k8s status",
  "attempt": 1,
  "final_answer": "...",
  "interrupt": null,
  "interrupt_message": null,
  "stop_message": null,
  "error": null,
  "model": null,
  "max_loops": null,
  "mcp": null,
  "created_at": "...",
  "updated_at": "..."
}
```

For `wait=false`, the initial response normally has `status: queued`.

## Resume Task

When a dangerous tool triggers an interrupt, the API stores interrupt metadata on the task and returns `status: interrupted`.

Resume by calling:

```http
POST /api/tasks/{task_id}/resume
```

Request:

```json
{
  "approved": true,
  "reason": "approved by operator",
  "wait": true
}
```

`wait=false` is also accepted on resume. In that case the approved task is queued and resumed by a background worker.

The source of truth for resume is the task record plus the internal LangGraph checkpoint `thread_id`. The user-facing `interrupt_message` is metadata for clients, not the checkpoint itself.

## Retry Task

`POST /api/tasks/{task_id}/retry`

Request:

```json
{
  "task_id": "optional-client-task-id",
  "reason": "operator requested retry",
  "wait": true
}
```

Retry is allowed only for terminal tasks: `completed`, `failed`, `stopped`, and `canceled`.

Retry creates a new task row. It does not reuse the old `task_id` or old LangGraph checkpoint. The new task copies the source task input, model configuration, MCP selection, session id, and max-loop setting.

Lineage fields:

```text
root_task_id
  first task in the retry chain

retry_of_task_id
  immediate source task for this retry

attempt
  ordered execution number within the retry chain
```

The source task records compact lifecycle events:

```text
task_retry_requested
task_retried
```

The retry task records the normal lifecycle events: `task_created`, `task_queued` or `task_started`, optional artifact events, and then a terminal event.

## Cancel Task

`POST /api/tasks/{task_id}/cancel`

Request:

```json
{
  "reason": "operator requested"
}
```

Cancellation is cooperative:

```text
queued / interrupted task
  -> canceled immediately

running task
  -> cancel_requested
  -> canceled at the next runtime safe boundary
```

Completed, failed, stopped, and canceled tasks are terminal and cannot be cancelled again.

## Task Events

`GET /api/tasks/{task_id}/events`

Task events are compact lifecycle records:

```text
task_created
task_queued
task_started
task_interrupted
task_resumed
task_retry_requested
task_retried
task_cancel_requested
task_cancelled
task_artifact_created
task_artifact_updated
task_completed
task_stopped
task_failed
```

The code-level event name contract is centralized in `vermay_agent/api/task_contract.py` as `TaskEventType`.

Task events are API-visible lifecycle data. They do not include raw model output, full prompts, raw graph state, final answer text, or full tool output.

Artifact events are compact references. For example, a completed task with a final answer records `task_artifact_created` before `task_completed`; the event payload includes artifact identifiers but not the final answer body.

## Task Artifacts

Completed tasks persist a default final-answer artifact in local SQLite metadata.

Current default artifact shape:

```json
{
  "artifact_id": "<task-id>:final_answer",
  "a2a_artifact_id": "final_answer",
  "name": "Final answer",
  "description": "Final text answer returned by the agent.",
  "parts": [
    {
      "text": "...",
      "mediaType": "text/plain"
    }
  ],
  "metadata": {
    "kind": "final_answer"
  },
  "extensions": []
}
```

The artifact table is the local output-source baseline for A2A-shaped artifact projection helpers. It is not exposed as a public HTTP endpoint yet.

## Task Event Stream

`GET /api/tasks/{task_id}/stream`

The stream endpoint is a local Server-Sent Events adapter over persisted `task_events`.

Stream behavior:

```text
1. Replay existing task events after the optional cursor.
2. Wait for newly persisted task events.
3. Stop when the task reaches a terminal status.
```

Cursor example:

```http
GET /api/tasks/{task_id}/stream?after=12
```

SSE fields:

```text
id: task event id
event: task event type
data: task event JSON
```

The stream does not emit model tokens, raw prompts, raw graph state, or full tool output.

## Optional A2A Routes

The default local API does not expose A2A routes. Start the server with explicit A2A support when needed:

```bash
vermay-agent serve --enable-a2a
```

When enabled, the server exposes:

```text
GET  /.well-known/agent-card.json
POST /message:send
GET  /tasks/{task_id}
POST /tasks/{task_id}:cancel
POST /tasks/{task_id}:subscribe
```

The A2A adapter is an API-edge adapter over existing local records:

```text
local task status -> A2A TaskState
local task event  -> A2A status update payload
local artifact    -> A2A artifact payload
local artifact event -> A2A artifact update payload
session/context   -> A2A contextId
task/run          -> A2A taskId
```

`thread_id` remains a LangGraph checkpoint implementation key and is not projected as an A2A identity. Local artifact events are kept out of the status projection and can be projected separately as artifact update payloads.

The A2A adapter translates A2A task/message/status requests into `AgentService` calls and projects persisted `TaskRecord`, `TaskEventRecord`, and `TaskArtifactRecord` data back into A2A payloads. It does not add A2A-specific nodes, routing, state keys, or protocol branches inside `vermay_agent/langgraph_runtime/`.

Current projection policy:

```text
created / queued -> TASK_STATE_SUBMITTED
running          -> TASK_STATE_WORKING
interrupted      -> TASK_STATE_INPUT_REQUIRED
cancel_requested -> TASK_STATE_WORKING
canceled         -> TASK_STATE_CANCELED
completed        -> TASK_STATE_COMPLETED
stopped / failed -> TASK_STATE_FAILED
```

`POST /tasks/{task_id}:subscribe` is a Server-Sent Events stream over persisted task events projected into A2A status/artifact update payloads. It does not emit model tokens.

## Runtime Contract

The API service uses task-oriented service methods:

```python
AgentService.create_session(...) -> SessionRecord
AgentService.start_task(session_id, input, task_id=None, options=None, wait=True) -> TaskRecord
AgentService.resume_task(task_id, approved, reason=None, wait=True) -> TaskRecord
AgentService.cancel_task(task_id, reason=None) -> TaskRecord
```

`RunResult` remains internal to runtime/service execution. HTTP responses are projected from persisted session/task metadata after the service saves the latest lifecycle state.

## Error Mapping

API routes map project error taxonomy to client-facing errors:

```text
invalid request / configuration -> 400
unknown session                 -> 404
unknown task                    -> 404
invalid lifecycle state         -> 409
unexpected runtime failure      -> 500
```

Unexpected runtime failures return a compact generic detail string and do not expose raw internal exception text.

Failed tasks are persisted with safe error metadata:

```text
error.code
error.message
```

Raw tracebacks and raw graph state are not exposed in API payloads.

## Service Ownership

`create_app()` has two ownership modes:

- When no service is provided, the app creates and closes its own `AgentService` and local `AgentStore`.
- When a service is injected, the caller owns that service lifecycle.

This keeps tests and embedded API usage from having resources closed unexpectedly by the FastAPI app factory.

## Lifecycle Observability

The API service emits compact lifecycle events through a `LifecycleObserver`.

Default app-created services write these events to the configured JSONL trace path. Injected services may use a custom observer or the null observer.

Lifecycle event payloads include:

```text
session_id
task_id
thread_id
operation
status
model_provider
max_loops
mcp_selected
duration_ms
error_code
```

Lifecycle events are for operational monitoring. They do not include raw user input, model output, final answer text, graph state, or full tool output.

## Current Boundaries

- No model-token streaming.
- No HTTP endpoints for memory, skills, eval replay, or MCP administration.
- No authentication in the local default server.
- No raw graph state exposure by default.
