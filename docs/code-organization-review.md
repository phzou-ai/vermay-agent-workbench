# Code Organization Review

## Scope

This review focuses on the current LangGraph runtime and shared harness modules.

No feature expansion is proposed here. The goal is to identify where the code structure should be tightened before more runtime capabilities are added.

## Current Assessment

The project is functionally stable for the current baseline:

- LangGraph is the default runtime.
- Tool execution is explicit and permission-gated.
- Approval interrupt/resume is implemented.
- Progress, stream inspection, and JSONL trace are available.
- ToolNode compatibility has been evaluated without replacing the active runtime path.

The main issue is not correctness. The main issue is that several files now carry mixed responsibilities.

## High-Priority Organization Issues

### 1. `mini_agent/langgraph_runtime/nodes.py` Is Too Broad

Current responsibilities:

- node factory definitions
- context build node
- model call node
- permission node
- approval interrupt node
- tool execution node
- observation node
- terminal progress event calls
- JSONL trace event calls
- LangGraph custom stream event calls
- Kubernetes command summary helper
- observation summary helper

Risk:

- Any change to a single node requires reading unrelated node concerns.
- Progress and trace formatting logic is mixed with orchestration logic.
- The file will become hard to extend if memory, RAG, skills, or model routing nodes are added.

Recommended next cleanup:

```text
mini_agent/langgraph_runtime/
  components.py
  nodes/
    context.py
    model.py
    permission.py
    approval.py
    tools.py
    observation.py
    step.py
  node_events.py
```

Do not do the full split immediately unless the next task touches these areas. A first safe step is to extract `GraphComponents` and node event helpers.

### 2. `runner.py` Mixes Runtime Lifecycle and Invocation Modes

Current responsibilities:

- holds runtime dependencies
- builds the compiled graph
- creates checkpointers
- builds initial state
- invokes graph normally
- invokes graph in stream mode
- resumes approval interrupts
- formats interrupt messages

Risk:

- checkpoint and stream handling are correct but tightly packed into the runtime wrapper.
- future additions such as session metadata, cancellation, or multiple resume types will make `runner.py` harder to read.

Recommended next cleanup:

```text
mini_agent/langgraph_runtime/
  runner.py
  checkpointing.py
  invocation.py
```

Lower-risk alternative:

- keep `runner.py` intact for now
- extract `_build_checkpointer` into `checkpointing.py`
- extract stream invocation into `streaming.py` beside the existing reporter helpers

### 3. Shared Harness Modules Remain Flat

Current state:

`mini_agent/` contains shared harness modules used by the LangGraph runtime:

- `context_builder.py`
- `tool_registry.py`
- `tool_executor.py`
- `permission.py`
- `observation.py`
- `trace.py`
- `progress.py`
- `types.py`

Risk:

- As more runtime features are added, the package root may become a broad collection of unrelated infrastructure.
- Moving all modules too early would create import churn without a concrete maintenance benefit.

Recommended cleanup:

Do not move packages yet. Moving modules now would create churn across imports and tests.

If the project grows, introduce a dedicated harness package later:

```text
mini_agent_core/
  context_builder.py
  tool_registry.py
  tool_executor.py
  permission.py
  observation.py
  trace.py
  progress.py
  types.py
```

This should wait until there is a concrete maintenance reason.

## Medium-Priority Issues

### Duplicate Summary Helpers

Runtime nodes need concise terminal summaries for:

- Kubernetes command summary
- tool exit code extraction
- observation stdout/stderr summary

Recommended cleanup:

Extract these into a shared helper module:

```text
mini_agent/result_summary.py
```

Status: completed. The LangGraph runtime uses `mini_agent/result_summary.py`.

### Tool Registration Files Are Serviceable but Growing

`mini_agent/tools/devops/registry.py` is already 100+ lines and contains all DevOps tool specs.

Recommended cleanup:

Do not split yet. If more DevOps tools are added, split specs by tool family:

```text
mini_agent/tools/devops/mock_registry.py
mini_agent/tools/devops/kubernetes_registry.py
mini_agent/tools/devops/dangerous_registry.py
```

### Tests Are Correct but Some Builders Are Repeated

Test files repeat runtime setup helpers and fake model classes.

Recommended cleanup:

Introduce test fixtures only if duplication starts blocking changes. Current duplication is acceptable because each test file remains readable.

## Current ToolNode Decision

`ToolNode` should not replace the active tool execution node yet.

The detailed compatibility evaluation has been moved to the companion `mini-agent-docs` workspace.

The adapter module is acceptable:

```text
mini_agent/langgraph_runtime/toolnode_adapter.py
```

It is not on the active runtime path. It records the shape conversion needed if the project later adopts LangChain message-native tool execution.

## Recommended Cleanup Order

1. Extract shared result summary helpers.
2. Extract `GraphComponents` from `nodes.py`.
3. Extract custom stream event helper from `nodes.py`.
4. Consider splitting `nodes.py` only when the next graph feature requires touching it.
5. Keep `runner.py` intact until checkpointing or stream invocation changes again.

## Do Not Do Yet

- Do not move all shared harness modules into a new package.
- Do not replace custom tool execution with `ToolNode`.
- Do not split every node into separate files before there is a concrete maintenance trigger.
- Do not add RAG, memory, MCP, A2A, or model routing during this cleanup pass.
