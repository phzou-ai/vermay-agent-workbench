from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

from mini_agent.langgraph_runtime import LangGraphAgentRuntime, ModelProviderConfig

from .app_factory import (
    DEFAULT_AGENT_STORE_PATH,
    DEFAULT_MCP_CONFIG_PATH,
    DEFAULT_SKILL_PROPOSALS_PATH,
    DEFAULT_SKILLS_PATH,
    ROOT,
    RuntimeFactoryConfig,
    build_runtime,
)
from .evaluation import TraceReplayService
from .mcp_client import MCPToolLoader
from .memory import SQLiteMemoryStore
from .skills import SkillStore
from .storage import AgentStore


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in {"memory", "skills", "eval", "mcp"}:
        _run_subcommand(sys.argv[1:])
        return

    _run_prompt(sys.argv[1:])


def _run_prompt(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Mini Agent Workbench")
    parser.add_argument("prompt", nargs="*", help="User input")
    parser.add_argument(
        "--trace",
        default="latest.jsonl",
        help="Trace JSONL filename or path under traces/. Absolute paths are allowed.",
    )
    parser.add_argument("--model-provider", default="ollama", help="Model provider adapter to use")
    parser.add_argument("--ollama-model", default=None, help="Override MINI_AGENT_OLLAMA_MODEL")
    parser.add_argument("--ollama-base-url", default=None, help="Override MINI_AGENT_OLLAMA_BASE_URL")
    parser.add_argument(
        "--ollama-timeout-seconds",
        type=int,
        default=None,
        help="Override MINI_AGENT_OLLAMA_TIMEOUT_SECONDS",
    )
    parser.add_argument(
        "--model-option",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Advanced model provider option. Can be repeated. Overrides provider-specific flags.",
    )
    parser.add_argument("--max-steps", type=int, default=5, help="Maximum model calls per run")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress logs on stderr")
    parser.add_argument("--thread-id", default=None, help="LangGraph checkpoint thread id")
    parser.add_argument(
        "--resume-approval",
        choices=["true", "false"],
        default=None,
        help="Resume a LangGraph approval interrupt with approval true or false",
    )
    parser.add_argument("--approval-reason", default=None, help="Optional reason for approval resume")
    args = parser.parse_args(argv)

    user_input = " ".join(args.prompt).strip() or "check cluster status"
    try:
        model_config = _model_provider_config_from_args(args)
        trace_path = _trace_path(args.trace)
    except ValueError as exc:
        parser.error(str(exc))

    runtime = build_runtime(
        RuntimeFactoryConfig(
            model=model_config,
            trace_path=trace_path,
            max_loops=args.max_steps,
            show_progress=not args.no_progress,
        )
    )

    try:
        if args.resume_approval is not None:
            if not args.thread_id:
                raise SystemExit("--thread-id is required with --resume-approval")
            approved = args.resume_approval == "true"
            print(runtime.resume(thread_id=args.thread_id, approved=approved, reason=args.approval_reason).to_output())
            return

        if sys.stdin.isatty():
            print(
                run_langgraph_with_interactive_approval(
                    runtime,
                    user_input,
                    _prompt_for_approval,
                    thread_id=args.thread_id,
                )
            )
            return

        print(runtime.run(user_input, thread_id=args.thread_id))
    finally:
        runtime.close()


def run_langgraph_with_interactive_approval(
    runtime: LangGraphAgentRuntime,
    user_input: str,
    approval_provider: Callable[[str, str], tuple[bool, str | None]],
    max_approval_rounds: int = 1,
    thread_id: str | None = None,
) -> str:
    result = runtime.start(user_input, thread_id=thread_id)
    approval_rounds = 0

    while result.interrupt_message is not None:
        approval_rounds += 1
        if approval_rounds > max_approval_rounds:
            message = f"Stopped after {max_approval_rounds} approval rounds."
            if runtime.trace is not None:
                runtime.trace.log_event("langgraph_approval_round_limit_reached", {"message": message})
            return message

        approved, reason = approval_provider(result.interrupt_message, result.thread_id)
        result = runtime.resume(thread_id=result.thread_id, approved=approved, reason=reason)

    return result.to_output()


def _prompt_for_approval(message: str, thread_id: str) -> tuple[bool, str | None]:
    for line in message.splitlines():
        if not line.startswith("Resume with:"):
            print(line)
    while True:
        try:
            value = input(f"Approve tool execution for thread {thread_id}? [yes/no]: ").strip().lower()
        except EOFError:
            return False, "approval input unavailable"
        if value in {"y", "yes"}:
            return True, "approved interactively"
        if value in {"n", "no"}:
            return False, "rejected interactively"
        print("Please enter yes or no.")


def _model_provider_config_from_args(args: argparse.Namespace) -> ModelProviderConfig:
    options: dict[str, object] = {}
    has_ollama_flags = any(
        value is not None
        for value in (
            args.ollama_model,
            args.ollama_base_url,
            args.ollama_timeout_seconds,
        )
    )
    if args.model_provider != "ollama" and has_ollama_flags:
        raise ValueError("ollama-specific CLI flags require --model-provider ollama")
    if args.model_provider == "ollama":
        if args.ollama_model is not None:
            options["model"] = args.ollama_model
        if args.ollama_base_url is not None:
            options["base_url"] = args.ollama_base_url
        if args.ollama_timeout_seconds is not None:
            options["timeout_seconds"] = args.ollama_timeout_seconds
    options.update(_parse_model_options(args.model_option))
    return ModelProviderConfig(provider=args.model_provider, options=options)


def _parse_model_options(values: list[str]) -> dict[str, str]:
    options: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"invalid --model-option '{value}'; expected KEY=VALUE")
        key, option_value = value.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"invalid --model-option '{value}'; key cannot be empty")
        options[key] = option_value
    return options


def _trace_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    trace_root = ROOT / "traces"
    target = (trace_root / path).resolve()
    if trace_root.resolve() not in target.parents and target != trace_root.resolve():
        raise ValueError("--trace relative path must stay under traces/")
    return target


def _run_subcommand(argv: list[str]) -> None:
    command = argv[0]
    if command == "memory":
        _run_memory_command(argv[1:])
        return
    if command == "skills":
        _run_skills_command(argv[1:])
        return
    if command == "eval":
        _run_eval_command(argv[1:])
        return
    if command == "mcp":
        _run_mcp_command(argv[1:])
        return
    raise SystemExit(f"unknown command: {command}")


def _run_memory_command(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="mini-agent memory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add")
    add_parser.add_argument("content")
    add_parser.add_argument("--tag", action="append", default=[])

    subparsers.add_parser("list")

    disable_parser = subparsers.add_parser("disable")
    disable_parser.add_argument("id", type=int)

    args = parser.parse_args(argv)
    store = AgentStore(DEFAULT_AGENT_STORE_PATH)
    try:
        memory = SQLiteMemoryStore(store)
        if args.command == "add":
            item = memory.add(args.content, tags=args.tag)
            print(f"added memory {item.id}")
        elif args.command == "list":
            for item in memory.list():
                status = "enabled" if item.enabled else "disabled"
                tags = ",".join(item.tags) if item.tags else "-"
                print(f"{item.id}\t{status}\t{tags}\t{item.content}")
        elif args.command == "disable":
            item = memory.disable(args.id)
            print(f"disabled memory {item.id}")
    finally:
        store.close()


def _run_skills_command(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="mini-agent skills")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list")
    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("name")
    propose_parser = subparsers.add_parser("propose-from-trace")
    propose_parser.add_argument("--trace", required=True)
    approve_parser = subparsers.add_parser("approve")
    approve_parser.add_argument("proposal_id")

    args = parser.parse_args(argv)
    store = AgentStore(DEFAULT_AGENT_STORE_PATH)
    try:
        skills = SkillStore(
            authored_dir=DEFAULT_SKILLS_PATH,
            proposals_dir=DEFAULT_SKILL_PROPOSALS_PATH,
            store=store,
        )
        if args.command == "list":
            for skill in skills.list_skills():
                triggers = ",".join(skill.triggers) if skill.triggers else "-"
                print(f"{skill.name}\t{skill.version}\t{triggers}\t{skill.description}")
        elif args.command == "show":
            skill = skills.show(args.name)
            print(skill.path.read_text(encoding="utf-8"), end="")
        elif args.command == "propose-from-trace":
            path = skills.propose_from_trace(Path(args.trace))
            print(f"created proposal {path.stem}")
        elif args.command == "approve":
            skill = skills.approve(args.proposal_id)
            print(f"approved skill {skill.name}")
    finally:
        store.close()


def _run_eval_command(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="mini-agent eval")
    subparsers = parser.add_subparsers(dest="command", required=True)
    replay_parser = subparsers.add_parser("replay")
    replay_source = replay_parser.add_mutually_exclusive_group(required=True)
    replay_source.add_argument("--trace")
    replay_source.add_argument("--scenario")
    subparsers.add_parser("list-runs")

    args = parser.parse_args(argv)
    store = AgentStore(DEFAULT_AGENT_STORE_PATH)
    try:
        service = TraceReplayService(store=store, report_dir=ROOT / "data" / "eval_runs")
        if args.command == "replay":
            if args.trace:
                report = service.replay_trace(Path(args.trace))
            else:
                report = service.replay_scenario(Path(args.scenario))
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        elif args.command == "list-runs":
            for run in service.list_runs():
                print(f"{run['id']}\t{run['status']}\t{run['source_type']}\t{run['source_path']}")
    finally:
        store.close()


def _run_mcp_command(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="mini-agent mcp")
    subparsers = parser.add_subparsers(dest="command", required=True)
    list_parser = subparsers.add_parser("list-tools")
    list_parser.add_argument("--config", default=str(DEFAULT_MCP_CONFIG_PATH))
    args = parser.parse_args(argv)

    if args.command == "list-tools":
        tools = MCPToolLoader(Path(args.config)).load_tools()
        for tool in tools:
            dangerous = bool((tool.metadata or {}).get("dangerous", False))
            print(f"{tool.name}\tdangerous={dangerous}\t{tool.description}")


if __name__ == "__main__":
    main()
