"""Tool implementations for the agent.

Each tool module exposes a ``register(agent)`` function matching
:data:`aviation_copilot.agent.core.ToolRegistrar`. The orchestrator at app
startup registers all four through :func:`register_all_tools`.

Tools and their domains:

- :mod:`flight_data`  — historical flight statistics (DuckDB, U2)
- :mod:`weather`      — current METAR/TAF (NOAA Aviation Weather)
- :mod:`notam`        — current NOTAMs (FAA / aviationweather.gov)
- :mod:`corpus`       — semantic search over FAA AIM (LanceDB, U3)
"""

from pydantic_ai import Agent

from aviation_copilot.agent.core import AgentDeps, register_tools
from aviation_copilot.tools import corpus, flight_data, notam, weather


def register_all_tools(agent: Agent[AgentDeps, str]) -> None:
    """Register all four production tools on ``agent``.

    Used by the FastAPI lifespan (U6) and by Modal's app entry (U11).
    Tests typically register stubs via :func:`register_tools` directly
    rather than calling this.
    """
    flight_data.register(agent)
    weather.register(agent)
    notam.register(agent)
    corpus.register(agent)


def register_default_registrars() -> None:
    """Add every tool module's ``register`` to the agent-core registrar list.

    Convenience for callers that use ``build_agent(apply_tool_registrars=True)``
    instead of registering against a specific Agent instance.
    """
    register_tools(
        flight_data.register,
        weather.register,
        notam.register,
        corpus.register,
    )


__all__ = [
    "corpus",
    "flight_data",
    "notam",
    "register_all_tools",
    "register_default_registrars",
    "weather",
]
