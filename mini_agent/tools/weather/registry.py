from __future__ import annotations

from mini_agent.tool_registry import ToolRegistry
from mini_agent.types import ToolSpec

from .forecast import weather_forecast


def register_weather_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="weather_forecast",
            description=(
                "Get current weather and a 1-3 day forecast for a city or location. "
                "Use this for weather, temperature, rain, wind, or forecast questions."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City or location, for example 'Shanghai', 'San Francisco', or 'Beijing'.",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of forecast days, between 1 and 3. Defaults to 3.",
                    },
                },
                "required": ["location"],
            },
            dangerous=False,
            func=weather_forecast,
        )
    )

