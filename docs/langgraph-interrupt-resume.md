# LangGraph Interrupt And Resume

## Scope

This document describes the current approval interrupt and resume flow in the LangGraph runtime.

The implementation is centered on:

- `mini_agent/langgraph_runtime/runner.py`
- `mini_agent/langgraph_runtime/nodes.py`
- `mini_agent/langgraph_runtime/graph.py`

## Runtime Entry

The CLI builds the LangGraph runtime through `build_langgraph_runtime()` in `mini_agent/main.py`.

Default execution path:

```text
mini-agent "<prompt>"
  -> main()
  -> build_langgraph_runtime()
  -> TTY: CLI run_with_interactive_approval(...)
  -> non-TTY: LangGraphAgentRuntime.run()
```

Manual approval resume path:

```text
mini-agent --thread-id <id> --resume-approval true
  -> main()
  -> build_langgraph_runtime()
  -> LangGraphAgentRuntime.resume_approval(thread_id=<id>)
```

## Initial Run

`LangGraphAgentRuntime.run()` creates a fresh graph state and delegates to `start()`:

```text
user_input
messages=[]
observations=[]
tool_call=None
permission_decision=None
approval_result=None
tool_result=None
observation=None
final_answer=None
step=1
max_steps=<configured max_steps>
errors=[]
```

`start()` then assigns a `thread_id`:

```text
provided thread_id
  or generated UUID
```

The `thread_id` is passed to LangGraph through:

```python
{"configurable": {"thread_id": thread_id}}
```

This value identifies the checkpoint lineage for the run. A single thread can contain multiple checkpoints as the graph advances.

## Invoke Versus Stream

The runtime has two execution modes:

```python
graph.invoke(...)
```

and:

```python
graph.stream(...)
```

Both modes support LangGraph `interrupt(...)`.

`invoke` returns after the graph either:

- finishes normally, or
- pauses at an interrupt.

`stream` emits graph runtime chunks while nodes execute. It is used for runtime inspection, not for enabling interrupt behavior.

The current `_invoke()` method uses:

```text
stream_modes is None
  -> graph.invoke(...)

stream_modes is not None
  -> graph.stream(...)
```

In stream mode, the runtime explicitly preserves `__interrupt__` chunks from `updates` so downstream interrupt handling can use the same `_extract_interrupt()` path.

## Approval Decision Point

Dangerous tools are stopped by `PermissionGate`.

Graph-level routing sends approval-required decisions to `approval_required_node()`:

```text
check_permission
  -> route_permission
  -> approval_required
```

Inside `approval_required_node()`, the node calls:

```python
interrupt(payload)
```

The payload contains the approval request:

```text
kind=approval_required
step=<current step>
tool_call=<tool call payload>
permission=<permission decision payload>
message=<human-readable approval message>
```

At this point LangGraph pauses graph execution and stores the current graph state through the configured checkpointer.

## `__interrupt__`

`__interrupt__` is a LangGraph runtime control field returned when execution pauses at `interrupt(...)`.

It is not part of the project-defined `AgentState`, and it should not be written as business state.

Current usage:

```python
interrupts = state.get("__interrupt__")
```

The runner reads this field in `_extract_interrupt()` to determine whether the graph paused for approval.

If present, the runner builds a `RunResult` with both the raw interrupt payload and a user-facing interrupt message.

## `RunResult.interrupt_message`

`RunResult.interrupt_message` is the CLI-facing approval message produced from LangGraph interrupt data.

It is not persisted in LangGraph checkpoint state. It is derived from the latest graph result.

Purpose:

```text
LangGraph interrupt result
  -> runtime extracts approval message
  -> runtime returns RunResult(interrupt=..., interrupt_message=...)
  -> CLI prompt displays it
  -> user approves or rejects
  -> runtime resumes the graph
```

The interactive approval wrapper uses the returned `RunResult` as control flow. If `result.interrupt_message` is present, it prompts for approval. If it is absent, the wrapper returns `result.to_output()`.

## Manual Resume

Manual resume uses:

```bash
mini-agent --thread-id <id> --resume-approval true
```

or:

```bash
mini-agent --thread-id <id> --resume-approval false
```

The runtime calls:

```python
graph.invoke(
    Command(resume={"approved": approved, "reason": reason}),
    config={"configurable": {"thread_id": thread_id}},
)
```

`Command(resume=...)` tells LangGraph to continue from the checkpointed interrupt for the specified `thread_id`.

The resume payload becomes the return value of the earlier `interrupt(...)` call inside `approval_required_node()`.

The node then stores:

```text
approval_result.approved
approval_result.reason
```

Routing continues from that result:

```text
approved=true
  -> execute_tool

approved=false
  -> reject_tool
```

## Interactive Resume

Interactive approval is the default CLI behavior when stdin is attached to a terminal. It is a CLI convenience wrapper around the same interrupt/resume mechanism.

Flow:

```text
CLI run_with_interactive_approval(...)
  -> runtime.start()
     -> graph.invoke(...) or graph.stream(...)
     -> RunResult with final answer or interrupt
  -> if interrupt exists:
       approval_provider(message, thread_id)
       runtime.resume(thread_id, approved, reason)
  -> return final answer
```

The CLI helper does not repeat an already-completed graph run. It starts the graph once through `start()`. It only resumes when the returned `RunResult` contains an interrupt message.

Current safety limit:

```text
max_approval_rounds=1
```

If the resumed graph hits another approval interrupt, the wrapper stops after the configured approval round limit instead of repeatedly prompting in the same terminal session.

When stdin is not a TTY, the CLI does not prompt. In that case `run()` returns the approval message and manual resume command instead.

## Checkpoint Storage

The CLI-backed runtime stores LangGraph checkpoints in:

```text
traces/langgraph_checkpoints.sqlite
```

The checkpoint contains graph state needed for resume. The terminal progress output and `RunResult.interrupt_message` are not the source of truth for resume.

The source of truth is:

```text
thread_id
checkpointer
Command(resume=...)
```

## Summary

The approval mechanism has two layers:

```text
LangGraph layer:
  interrupt(...)
  __interrupt__
  checkpoint
  Command(resume=...)

CLI/runtime layer:
  _extract_interrupt()
  RunResult.interrupt_message
  interactive yes/no prompt
  resume_approval()
```

`graph.invoke(...)` is suitable for approval interrupt scenarios. `graph.stream(...)` adds runtime visibility but is not required for interrupt/resume correctness.
