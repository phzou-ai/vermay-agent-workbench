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
  -> TTY: LangGraphAgentRuntime.run_with_interactive_approval()
  -> non-TTY: LangGraphAgentRuntime.run()
```

Manual approval resume path:

```text
mini-agent --thread-id <id> --resume-approval true
  -> main()
  -> build_langgraph_runtime(thread_id=<id>)
  -> LangGraphAgentRuntime.resume_approval()
```

## Initial Run

`LangGraphAgentRuntime.run()` creates a fresh graph state:

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

It then assigns a `thread_id`:

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

In stream mode, the runtime explicitly preserves `__interrupt__` chunks from `updates` so downstream interrupt handling can use the same `_extract_interrupt_message()` path.

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

The runner reads this field in `_extract_interrupt_message()` to determine whether the graph paused for approval.

If present, the runner builds a user-facing message and stores it in `_pending_interrupt_message`.

## `_pending_interrupt_message`

`_pending_interrupt_message` is runtime-local state used by the CLI interactive approval wrapper.

It is not persisted in LangGraph checkpoint state.

Purpose:

```text
LangGraph interrupt result
  -> runtime extracts approval message
  -> runtime stores pending message in _pending_interrupt_message
  -> CLI prompt displays it
  -> user approves or rejects
  -> runtime resumes the graph
```

The field is set only when `_extract_interrupt_message()` sees `__interrupt__`.

It is cleared when:

- a new run starts,
- resume starts,
- the latest graph result has no interrupt.

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
run_with_interactive_approval()
  -> run()
     -> graph.invoke(...)
     -> normal final answer or interrupt
  -> if interrupt exists:
       approval_provider(message, thread_id)
       resume_approval(approved, thread_id, reason)
  -> return final answer
```

`run_with_interactive_approval()` does not repeat an already-completed graph run. It starts the graph once through `run()`. It only resumes when `run()` stops at an interrupt and sets `_pending_interrupt_message`.

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

The checkpoint contains graph state needed for resume. The terminal progress output and `_pending_interrupt_message` are not the source of truth for resume.

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
  _extract_interrupt_message()
  _pending_interrupt_message
  interactive yes/no prompt
  resume_approval()
```

`graph.invoke(...)` is suitable for approval interrupt scenarios. `graph.stream(...)` adds runtime visibility but is not required for interrupt/resume correctness.
