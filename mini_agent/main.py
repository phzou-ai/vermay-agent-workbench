from __future__ import annotations

import sys

from .cli.prompt import (
    _model_provider_config_from_args,
    _parse_model_options,
    _trace_path,
    run_langgraph_with_interactive_approval,
    run_prompt,
)
from .cli.subcommands import run_serve_command as _run_serve_command
from .cli.subcommands import run_subcommand

_run_prompt = run_prompt
_run_subcommand = run_subcommand


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in {"serve", "memory", "skills", "eval", "mcp"}:
        run_subcommand(sys.argv[1:])
        return

    run_prompt(sys.argv[1:])


if __name__ == "__main__":
    main()
