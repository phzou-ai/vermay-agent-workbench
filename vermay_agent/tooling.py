from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict

from .tool_schema import DANGEROUS_METADATA_KEY


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


def structured_tool(
    *,
    func: Callable[..., Any],
    name: str,
    description: str,
    args_schema: type[BaseModel],
    dangerous: bool = False,
) -> StructuredTool:
    return StructuredTool.from_function(
        func=func,
        name=name,
        description=description,
        args_schema=args_schema,
        metadata={DANGEROUS_METADATA_KEY: dangerous},
    )
