# Project Overview

## Purpose

Mini Agent Workbench is a Python agent runtime for validating agent system behavior in realistic command-line workflows.

The current implementation focuses on:

- LangGraph-based orchestration.
- LangChain / LangGraph standard message types.
- Tool registration with LangGraph `ToolNode` execution.
- Tool schemas defined once through Pydantic `args_schema` on `StructuredTool`.
- Permission checks before dangerous operations.
- Approval interrupt and SQLite-backed resume in the CLI runtime.
- Human-readable progress output.
- Machine-readable JSONL trace output.
- SSH-backed read-only Kubernetes inspection.
- External read-only data tools such as weather forecast.

## Current Runtime Position

The CLI runtime is `mini_agent/langgraph_runtime/`.

The earlier hands-on runtime has been archived under `archive/hands_on_langgraph_runtime/`. It remains useful as historical reference material for explicit harness mechanics, but it is not an active runtime path.

## Primary Runtime Flow

```text
CLI input
  -> build runtime
  -> build initial graph state
  -> call model
  -> route final answer or tool call
  -> check permission
  -> execute safe tool or interrupt for approval
  -> record tool message
  -> continue or finish
```

## Runtime Guarantees

- Tool execution goes through LangGraph `ToolNode` after project permission checks.
- Model-facing tool schemas are derived from the same `StructuredTool` objects that `ToolNode` executes.
- Dangerous tools are intercepted by `PermissionGate`.
- Real cluster operations are limited to allowlisted read-only Kubernetes commands.
- SSH identity file paths are redacted in command traces.
- CLI checkpoint files are stored under `data/checkpoints/` and are not intended for Git.
- Local trace outputs are not intended for Git.

## Current Non-Goals

- Arbitrary SSH command execution.
- Unreviewed execution of dangerous tools.
- Production deployment packaging.
- MCP / A2A integration.
- Long-term memory policy.
- Multi-model routing.
- Self-evolving skill publication.
