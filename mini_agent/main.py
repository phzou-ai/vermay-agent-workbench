from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Sequence

from mini_agent.langgraph_runtime import LangGraphAgentRuntime
from mini_agent.langgraph_runtime.streaming import GraphStreamReporter, parse_stream_modes
from mini_agent.standard_runtime import (
    StandardLangGraphAgentRuntime,
    StandardOllamaModelClient,
    tool_spec_to_structured_tool,
)

from .context_builder import ContextBuilder
from .memory import MemoryStore
from .model_clients import OllamaModelClient
from .observation import ObservationHandler
from .permission import PermissionGate
from .progress import ProgressReporter
from .tool_executor import ToolExecutor
from .tool_registry import ToolRegistry
from .tools.devops import register_devops_tools
from .tools.weather import register_weather_tools
from .trace import TraceLogger


ROOT = Path(__file__).resolve().parents[1]


def build_langgraph_runtime(
    trace_name: str = "latest.jsonl",
    ollama_model: str | None = None,
    ollama_base_url: str | None = None,
    ollama_timeout_seconds: int | None = None,
    max_steps: int = 5,
    show_progress: bool = True,
    show_graph_stream: bool = False,
) -> LangGraphAgentRuntime:
    registry = ToolRegistry()
    register_devops_tools(registry)
    register_weather_tools(registry)

    return LangGraphAgentRuntime(
        model=OllamaModelClient(
            model=ollama_model,
            base_url=ollama_base_url,
            timeout_seconds=ollama_timeout_seconds,
        ),
        registry=registry,
        context_builder=ContextBuilder(),
        permission_gate=PermissionGate(registry),
        tool_executor=ToolExecutor(registry),
        observation_handler=ObservationHandler(),
        memory=MemoryStore(ROOT / "data" / "memory.txt"),
        trace=TraceLogger(ROOT / "traces" / trace_name),
        max_steps=max_steps,
        progress=ProgressReporter(enabled=show_progress),
        stream_reporter=GraphStreamReporter(enabled=show_graph_stream),
        checkpoint_path=ROOT / "traces" / "langgraph_checkpoints.sqlite",
    )


def build_standard_runtime(
    trace_name: str = "latest.jsonl",
    ollama_model: str | None = None,
    ollama_base_url: str | None = None,
    ollama_timeout_seconds: int | None = None,
    max_steps: int = 5,
    show_progress: bool = True,
) -> StandardLangGraphAgentRuntime:
    registry = ToolRegistry()
    register_devops_tools(registry)
    register_weather_tools(registry)
    tools = [tool_spec_to_structured_tool(registry.get(name)) for name in registry.names()]
    model = StandardOllamaModelClient(
        client=OllamaModelClient(
            model=ollama_model,
            base_url=ollama_base_url,
            timeout_seconds=ollama_timeout_seconds,
        ),
        tool_schemas=registry.schemas(),
    )

    return StandardLangGraphAgentRuntime(
        model=model,
        tools=tools,
        permission_gate=PermissionGate(registry),
        system_prompt=_default_system_prompt(),
        trace=TraceLogger(ROOT / "traces" / trace_name),
        max_loops=max_steps,
        progress=ProgressReporter(enabled=show_progress),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Mini Agent Workbench")
    parser.add_argument("prompt", nargs="*", help="User input")
    parser.add_argument("--trace", default="latest.jsonl", help="Trace JSONL filename")
    parser.add_argument("--ollama-model", default=None, help="Override MINI_AGENT_OLLAMA_MODEL")
    parser.add_argument("--ollama-base-url", default=None, help="Override MINI_AGENT_OLLAMA_BASE_URL")
    parser.add_argument(
        "--ollama-timeout-seconds",
        type=int,
        default=None,
        help="Override MINI_AGENT_OLLAMA_TIMEOUT_SECONDS",
    )
    parser.add_argument("--max-steps", type=int, default=5, help="Maximum model calls per run")
    parser.add_argument(
        "--runtime",
        choices=["reference", "langgraph", "standard"],
        default="reference",
        help="Runtime implementation to use. 'langgraph' is an alias for 'reference'.",
    )
    parser.add_argument("--no-progress", action="store_true", help="Disable progress logs on stderr")
    parser.add_argument("--thread-id", default=None, help="LangGraph checkpoint thread id")
    parser.add_argument(
        "--resume-approval",
        choices=["true", "false"],
        default=None,
        help="Resume a LangGraph approval interrupt with approval true or false",
    )
    parser.add_argument("--approval-reason", default=None, help="Optional reason for approval resume")
    parser.add_argument(
        "--graph-stream",
        action="store_true",
        help="Show concise LangGraph stream debug events instead of harness progress logs",
    )
    parser.add_argument(
        "--graph-stream-mode",
        action="append",
        default=None,
        help="LangGraph stream mode to inspect. Repeat or use comma-separated values: updates, values, debug, custom",
    )
    args = parser.parse_args()

    user_input = " ".join(args.prompt).strip() or "check cluster status"
    use_graph_stream = args.graph_stream or args.graph_stream_mode is not None
    if args.runtime == "standard" and use_graph_stream:
        raise SystemExit("--graph-stream is only supported by the reference runtime")

    show_progress = not args.no_progress and not use_graph_stream
    runtime_name = "reference" if args.runtime == "langgraph" else args.runtime

    if runtime_name == "standard":
        runtime = build_standard_runtime(
            trace_name=args.trace,
            ollama_model=args.ollama_model,
            ollama_base_url=args.ollama_base_url,
            ollama_timeout_seconds=args.ollama_timeout_seconds,
            max_steps=args.max_steps,
            show_progress=show_progress,
        )
    else:
        runtime = build_langgraph_runtime(
            trace_name=args.trace,
            ollama_model=args.ollama_model,
            ollama_base_url=args.ollama_base_url,
            ollama_timeout_seconds=args.ollama_timeout_seconds,
            max_steps=args.max_steps,
            show_progress=show_progress,
            show_graph_stream=use_graph_stream,
        )

    if args.resume_approval is not None:
        if not args.thread_id:
            raise SystemExit("--thread-id is required with --resume-approval")
        approved = args.resume_approval == "true"
        if runtime_name == "standard":
            print(runtime.resume(thread_id=args.thread_id, approved=approved, reason=args.approval_reason).to_output())
        else:
            print(runtime.resume_approval(thread_id=args.thread_id, approved=approved, reason=args.approval_reason))
        return

    stream_modes = parse_stream_modes(args.graph_stream_mode) if use_graph_stream else None

    if sys.stdin.isatty():
        if runtime_name == "standard":
            print(
                run_standard_with_interactive_approval(
                    runtime,
                    user_input,
                    _prompt_for_approval,
                    thread_id=args.thread_id,
                )
            )
        else:
            print(
                run_with_interactive_approval(
                    runtime,
                    user_input,
                    _prompt_for_approval,
                    stream_modes=stream_modes,
                    thread_id=args.thread_id,
                )
            )
        return

    if runtime_name == "standard":
        print(runtime.run(user_input, thread_id=args.thread_id))
    else:
        print(runtime.run(user_input, stream_modes=stream_modes, thread_id=args.thread_id))


def run_with_interactive_approval(
    runtime: LangGraphAgentRuntime,
    user_input: str,
    approval_provider: Callable[[str, str], tuple[bool, str | None]],
    skills: list[str] | None = None,
    stream_modes: Sequence[str] | None = None,
    max_approval_rounds: int = 1,
    thread_id: str | None = None,
) -> str:
    result = runtime.start(user_input, skills=skills, stream_modes=stream_modes, thread_id=thread_id)
    approval_rounds = 0

    while result.interrupt_message is not None:
        approval_rounds += 1
        if approval_rounds > max_approval_rounds:
            message = f"Stopped after {max_approval_rounds} approval rounds."
            runtime.trace.log_event("langgraph_approval_round_limit_reached", {"message": message})
            return message

        approved, reason = approval_provider(result.interrupt_message, result.thread_id)
        result = runtime.resume(thread_id=result.thread_id, approved=approved, reason=reason)

    return result.to_output()


def run_standard_with_interactive_approval(
    runtime: StandardLangGraphAgentRuntime,
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
                runtime.trace.log_event("standard_approval_round_limit_reached", {"message": message})
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


def _default_system_prompt() -> str:
    return ContextBuilder().build(user_input="", memory=[], skills=[], observations=[])[0].content


if __name__ == "__main__":
    main()
