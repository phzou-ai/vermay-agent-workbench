# ToolNode Evaluation

## Objective

Evaluate whether the LangGraph runtime should adopt the prebuilt `ToolNode` for tool execution.

The current runtime keeps tool execution explicit:

```text
call_model
  -> check_permission
  -> execute_tool
  -> handle_observation
```

This document records the current comparison result and the decision boundary for future adoption.

## Current Custom Execution Path

The active graph uses `execute_tool_node` in `mini_agent_langgraph/nodes.py`.

Execution path:

```text
ToolCall
  -> PermissionGate.check(...)
  -> ToolExecutor.execute(...)
  -> ToolResult
  -> ObservationHandler.process(...)
  -> Observation
  -> next model context
```

Properties:

- Preserves the project `ToolRegistry`.
- Keeps `PermissionGate` explicit before execution.
- Converts tool failures into `ToolResult(ok=False, error=...)`.
- Keeps observation formatting as a separate project-level layer.
- Writes project-specific trace and progress events.

## ToolNode Adapter Evaluation

The isolated adapter evaluation lives in:

```text
mini_agent_langgraph/toolnode_adapter.py
tests/test_toolnode_adapter.py
```

It does not modify the active graph.

The adapter tests validate this path:

```text
mini_agent.types.ToolCall
  -> LangChain AIMessage(tool_calls=[...])
  -> LangGraph ToolNode
  -> LangChain ToolMessage
```

Observed output shape:

```text
AIMessage(tool_calls=[...])
ToolMessage(content='{"value": "hello"}', name='echo', tool_call_id='call-adapter-test', status='success')
```

Observed error shape when `handle_tool_errors=True`:

```text
ToolMessage(
  content="Error: ValueError('bad value')\n Please fix your mistakes.",
  name='fail',
  status='error'
)
```

## Findings

`ToolNode` is compatible with the project if the current `ToolCall` is adapted into `AIMessage.tool_calls`.

Direct `ToolNode.invoke([...tool_calls...])` is not the preferred integration path for this project. In the installed LangGraph version, the stable path is to run `ToolNode` inside a graph with a messages state.

`ToolNode` returns `ToolMessage`, not the project `ToolResult`. Adopting it would require either:

- changing the graph state to standard LangChain messages, or
- adding an adapter from `ToolMessage` back to project-level `ToolResult` / `Observation`.

`ToolNode` does not replace permission checks. If a dangerous tool call is passed directly to `ToolNode`, it executes. The project must keep `PermissionGate` before any `ToolNode` execution.

`ToolNode` can simplify standard tool execution, parallel tool calls, and LangChain message compatibility. It also shifts some error-handling semantics into LangGraph/LangChain types.

## Decision

Do not replace the active custom `execute_tool_node` yet.

Keep the current custom execution node as the main runtime path until the project decides whether to move more of the graph state to standard LangChain message types.

`ToolNode` remains a candidate for a later integration, with this required boundary:

```text
check_permission must remain before ToolNode
```

## Adoption Criteria

Adopt `ToolNode` only if the project accepts the following changes:

- Convert model output into `AIMessage.tool_calls`.
- Represent tool output as `ToolMessage` or add a clear adapter back to `ToolResult`.
- Preserve project-specific `ObservationHandler`.
- Preserve project-specific trace and progress events.
- Keep dangerous tool approval outside and before `ToolNode`.

## Next Step

Keep the adapter tests as a compatibility guard.

Future work should focus on a small adapter design:

```text
Parsed ModelResponse
  -> AIMessage(tool_calls=[...])
  -> PermissionGate
  -> ToolNode
  -> ToolMessage
  -> ObservationHandler adapter
```

No main graph replacement is recommended at this point.
