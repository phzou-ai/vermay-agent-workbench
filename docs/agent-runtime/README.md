# Agent Runtime

## Scope

This domain documents the Mini Agent Workbench runtimes.

The runtime was created to study and verify the mechanics of an agent harness:

- context construction
- model invocation
- tool selection
- permission checks
- tool execution
- observation handling
- trace logging
- loop control

The handwritten runtime is a Phase 1 learning implementation. The LangGraph runtime is now the default CLI runtime.

## Reading Order

1. [current-state.md](current-state.md) - current implementation, decisions, deferred work, and next step.
2. [langgraph-implementation-plan.md](langgraph-implementation-plan.md) - evaluated Phase 2 plan and batch implementation order.
3. [../../README.md](../../README.md) - CLI usage, environment setup, tool examples, and repository structure.
4. Runtime entry points:
   - [../../mini_agent/runtime.py](../../mini_agent/runtime.py)
   - [../../mini_agent/main.py](../../mini_agent/main.py)
   - [../../mini_agent/context_builder.py](../../mini_agent/context_builder.py)
   - [../../mini_agent/model_clients/ollama.py](../../mini_agent/model_clients/ollama.py)
   - [../../mini_agent/tool_registry.py](../../mini_agent/tool_registry.py)
   - [../../mini_agent/tool_executor.py](../../mini_agent/tool_executor.py)
   - [../../mini_agent/permission.py](../../mini_agent/permission.py)
   - [../../mini_agent/observation.py](../../mini_agent/observation.py)
   - [../../mini_agent/trace.py](../../mini_agent/trace.py)
   - [../../mini_agent/progress.py](../../mini_agent/progress.py)

## Current Position

The handwritten runtime is working as a compact harness reference. It can run through the full loop from user input to model call, tool call, permission gate, tool execution, observation injection, rebuilt context, and final answer.

Current capabilities include:

- Ollama model adapter with `deepseek-v4-flash:cloud` as the default model.
- Mock DevOps tools for local learning scenarios.
- SSH-backed read-only Kubernetes tools for real cluster inspection.
- Weather forecast tool as a safe external data source.
- Rich terminal trace for human-readable harness inspection.
- Optional LangGraph stream inspection for graph-level events.
- JSONL trace for complete machine-readable run history.

## Recommended Next Step

Proceed to Batch 5: evaluate whether LangGraph `ToolNode` should be adopted.

The LangGraph implementation should live in a separate top-level package:

```text
mini_agent_langgraph/
```

The existing `mini_agent/` package remains the handwritten runtime baseline and shared harness module source.

The concrete batch plan is recorded in [langgraph-implementation-plan.md](langgraph-implementation-plan.md).

## Do Not Expand Yet

Do not add MCP, A2A, self-evolving behavior, complex memory, or arbitrary SSH execution before the LangGraph baseline and ToolNode decision are recorded.
