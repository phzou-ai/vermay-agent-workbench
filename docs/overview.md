# Project Overview

## Purpose

Mini Agent Workbench is a Python agent runtime for validating agent system behavior in realistic command-line workflows.

The current implementation focuses on:

- LangGraph-based orchestration.
- Explicit tool registration and execution.
- Permission checks before dangerous operations.
- Approval interrupt and resume.
- Observation handling after tool execution.
- Human-readable progress output.
- Machine-readable JSONL trace output.
- SSH-backed read-only Kubernetes inspection.
- External read-only data tools such as weather forecast.

## Current Runtime Position

The default CLI runtime is the LangGraph implementation in `mini_agent/langgraph_runtime/`.

The handwritten runtime in `mini_agent/runtime.py` remains in the repository as a compact reference implementation and compatibility path. New orchestration work should target the LangGraph runtime first.

## Primary Runtime Flow

```text
CLI input
  -> build runtime
  -> build initial graph state
  -> build context
  -> call model
  -> route final answer or tool call
  -> check permission
  -> execute safe tool or interrupt for approval
  -> handle observation
  -> rebuild context
  -> produce final answer
```

## Runtime Guarantees

- Tool execution goes through `ToolRegistry` and `ToolExecutor`.
- Dangerous tools are intercepted by `PermissionGate`.
- Real cluster operations are limited to allowlisted read-only Kubernetes commands.
- SSH identity file paths are redacted in command traces.
- Checkpoint files and local trace outputs are not intended for Git.

## Current Non-Goals

- Arbitrary SSH command execution.
- Unreviewed execution of dangerous tools.
- Production deployment packaging.
- MCP / A2A integration.
- Long-term memory policy.
- Multi-model routing.
- Self-evolving skill publication.

