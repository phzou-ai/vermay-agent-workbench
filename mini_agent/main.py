from __future__ import annotations

import argparse
from pathlib import Path

from mini_agent_langgraph import LangGraphAgentRuntime
from mini_agent_langgraph.streaming import GraphStreamReporter, parse_stream_modes

from .context_builder import ContextBuilder
from .memory import MemoryStore
from .model_clients import OllamaModelClient
from .observation import ObservationHandler
from .permission import PermissionGate
from .progress import ProgressReporter
from .runtime import MiniAgentRuntime
from .tool_executor import ToolExecutor
from .tool_registry import ToolRegistry
from .tools.devops import register_devops_tools
from .tools.weather import register_weather_tools
from .trace import TraceLogger


ROOT = Path(__file__).resolve().parents[1]


def build_runtime(
    trace_name: str = "latest.jsonl",
    ollama_model: str | None = None,
    ollama_base_url: str | None = None,
    ollama_timeout_seconds: int | None = None,
    max_steps: int = 5,
    show_progress: bool = True,
) -> MiniAgentRuntime:
    registry = ToolRegistry()
    register_devops_tools(registry)
    register_weather_tools(registry)

    return MiniAgentRuntime(
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
    )


def build_langgraph_runtime(
    trace_name: str = "latest.jsonl",
    ollama_model: str | None = None,
    ollama_base_url: str | None = None,
    ollama_timeout_seconds: int | None = None,
    max_steps: int = 5,
    show_progress: bool = True,
    thread_id: str | None = None,
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
        thread_id=thread_id,
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
        help="Show concise LangGraph stream events in addition to harness progress logs",
    )
    parser.add_argument(
        "--graph-stream-mode",
        action="append",
        default=None,
        help="LangGraph stream mode to inspect. Repeat or use comma-separated values: updates, values, debug, custom",
    )
    parser.add_argument(
        "--runtime",
        choices=["handwritten", "langgraph"],
        default="langgraph",
        help="Runtime implementation to use",
    )
    args = parser.parse_args()

    user_input = " ".join(args.prompt).strip() or "check cluster status"
    use_graph_stream = args.graph_stream or args.graph_stream_mode is not None
    if use_graph_stream and args.runtime != "langgraph":
        raise SystemExit("--graph-stream is only supported with --runtime langgraph")

    build = build_langgraph_runtime if args.runtime == "langgraph" else build_runtime
    runtime = build(
        trace_name=args.trace,
        ollama_model=args.ollama_model,
        ollama_base_url=args.ollama_base_url,
        ollama_timeout_seconds=args.ollama_timeout_seconds,
        max_steps=args.max_steps,
        show_progress=not args.no_progress,
        **(
            {"thread_id": args.thread_id, "show_graph_stream": use_graph_stream}
            if build is build_langgraph_runtime
            else {}
        ),
    )
    if args.resume_approval is not None:
        if args.runtime != "langgraph":
            raise SystemExit("--resume-approval is only supported with --runtime langgraph")
        if not args.thread_id:
            raise SystemExit("--thread-id is required with --resume-approval")
        approved = args.resume_approval == "true"
        print(runtime.resume_approval(approved=approved, thread_id=args.thread_id, reason=args.approval_reason))
        return

    if use_graph_stream:
        stream_modes = parse_stream_modes(args.graph_stream_mode)
        print(runtime.run(user_input, stream_modes=stream_modes))
        return

    print(runtime.run(user_input))


if __name__ == "__main__":
    main()
