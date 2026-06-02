# Project Overview

## Purpose

Mini Agent Workbench is a Python agent runtime for validating agent system behavior in realistic command-line and local API workflows.

The current implementation focuses on:

- LangGraph-based orchestration.
- LangChain / LangGraph standard message types.
- Tool registration with LangGraph `ToolNode` execution.
- Tool schemas defined once through Pydantic `args_schema` on `StructuredTool`.
- Permission checks before dangerous operations.
- Approval interrupt and SQLite-backed resume in the CLI runtime.
- Human-readable progress output.
- Machine-readable JSONL trace output.
- Local SQLite metadata for memory, skills, eval runs, and model profiles.
- Explicit-write memory injection.
- Authored markdown skills and generated skill proposals.
- Evaluation replay from traces or scenario fixtures without live tool execution.
- OpenAI-compatible model adapters and deterministic rule-based routing.
- MCP client-side tool discovery for configured servers.
- Local FastAPI server for agent session lifecycle.
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
- LangGraph checkpoint files are stored under `data/checkpoints/` and are not intended for Git.
- API session metadata is stored in `data/agent.sqlite`.
- The local metadata schema currently records version `1` in `schema_migrations`.
- Local trace outputs are not intended for Git.
- Evaluation replay defaults to recorded trace/scenario data and does not execute a live model or live tools.
- Memory writes are explicit CLI operations only.
- MCP servers are inactive by default and must be selected per run; selected MCP tools require approval unless marked read-only in configuration.

## Local Storage

The project uses SQLite for metadata and files for larger artifacts:

- `data/agent.sqlite`: memory items, skill index, eval run metadata, model profile metadata, and API session metadata.
- `data/checkpoints/langgraph.sqlite`: LangGraph checkpoint state for interrupt/resume.
- `skills/*.md`: authored skills tracked with the project.
- `data/skill_proposals/*.md`: generated skill proposals, local-only by default.
- `evals/scenarios/*.json`: replay scenario fixtures tracked with the project.
- `data/eval_runs/*.json`: generated replay reports, local-only by default.
- `config/mcp_servers.json`: configured MCP clients.
- `config/model_profiles.json`: model profiles and router rules.

## Current Non-Goals

- Arbitrary SSH command execution.
- Unreviewed execution of dangerous tools.
- Production deployment packaging.
- Public unauthenticated API exposure.
- A2A integration.
- Automatic long-term memory writes.
- Vector search or embedding-backed memory retrieval.
- Dynamic MCP server installation.
- Self-evolving skill publication without review.
