# Vermay Agent Workbench Documentation

## Scope

This directory contains stable project-facing documentation for Vermay Agent Workbench.

The project is positioned as an agent validation and practice workbench. It provides a concrete runtime for testing agent orchestration, tool execution, approval control, memory, skills, evaluation replay, model adapters, MCP client integration, local API integration, and real-world tool patterns.

## Reading Order

1. [overview.md](overview.md) - project purpose, current capabilities, and operating model.
2. [modules.md](modules.md) - key packages and module responsibilities.
3. [operations.md](operations.md) - CLI usage, runtime options, environment configuration, and traces.
4. [langgraph-interrupt-resume.md](langgraph-interrupt-resume.md) - approval interrupt, checkpoint, and resume flow.
5. [server-api-readiness.md](server-api-readiness.md) - local API surface, session metadata, and approval resume contract.
6. [code-organization-review.md](code-organization-review.md) - current code organization assessment and cleanup order.

## Documentation Boundary

Repository docs should describe the current project and its stable module boundaries.

Historical planning notes, batch implementation records, and broader roadmap material are kept outside this repository in the companion `mini-agent-docs` workspace.

Archived implementation material retained in this repository is kept under `archive/` and is not part of the active runtime or default test suite.
