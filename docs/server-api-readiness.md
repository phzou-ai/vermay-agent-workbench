# Server/API

## Current API Surface

The project includes a local FastAPI server for agent lifecycle operations.

Start the server:

```bash
mini-agent serve
```

Default bind address:

```text
127.0.0.1:8000
```

Endpoints:

```text
GET  /health
POST /sessions
GET  /sessions/{thread_id}
POST /sessions/{thread_id}/resume
```

The first API batch is local-only and does not add authentication. Do not expose it beyond a trusted local environment without adding an access-control layer.

## Start Session

`POST /sessions`

Request:

```json
{
  "input": "check k8s status",
  "thread_id": "optional-client-session-id",
  "max_loops": 5,
  "model": {
    "provider": "ollama",
    "options": {
      "model": "deepseek-v4-flash:cloud"
    }
  }
}
```

Only `input` is required. When omitted, `thread_id`, `max_loops`, and `model` use runtime defaults.

## Runtime Contract

The API uses the structured runtime methods:

```python
start(user_input, thread_id=None) -> RunResult
resume(thread_id, approved, reason=None) -> RunResult
```

Compatibility methods that return strings remain available for CLI use, but API code should use `RunResult` payloads.

## Session Mapping

The API uses `thread_id` as the external session identifier.

```text
HTTP session id
  -> LangGraph thread_id
  -> SQLite checkpoint state
```

Session metadata is persisted in `data/agent.sqlite`. LangGraph checkpoint state is persisted in `data/checkpoints/langgraph.sqlite`.

Stored session metadata includes:

- `thread_id`
- `input`
- `status`
- `final_answer`
- `interrupt`
- `interrupt_message`
- `stop_message`
- `created_at`
- `updated_at`

Raw graph state is not stored or returned by default.

## Response Shape

`POST /sessions` and `POST /sessions/{thread_id}/resume` return `RunResult.to_dict()`:

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

`GET /sessions/{thread_id}` returns stored metadata:

```json
{
  "thread_id": "session-a",
  "status": "interrupted",
  "input": "run a dangerous operation",
  "final_answer": null,
  "interrupt": {},
  "interrupt_message": "Approval required...",
  "stop_message": null,
  "created_at": "...",
  "updated_at": "..."
}
```

Status values:

```text
completed
interrupted
stopped
unknown
```

## Approval Resume

When a dangerous tool triggers an interrupt, the API stores the interrupt metadata and returns `status: interrupted`.

Resume by calling:

```http
POST /sessions/{thread_id}/resume
```

Request:

```json
{
  "approved": true,
  "reason": "approved by operator"
}
```

The source of truth for resume is the `thread_id` plus the LangGraph checkpoint store. The user-facing `interrupt_message` is metadata for clients, not the checkpoint itself.

## Current Boundaries

- No server-side streaming.
- No HTTP endpoints for memory, skills, eval replay, or MCP.
- No authentication in the local default server.
- No raw graph state exposure by default.
