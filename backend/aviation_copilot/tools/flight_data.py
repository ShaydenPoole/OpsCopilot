"""``flight_data_query`` tool — historical BTS flight statistics.

Wraps :class:`aviation_copilot.data.duckdb_client.DuckDBClient` (U2) and
returns a structured RouteSummary the agent can quote verbatim. The agent
calls this tool for questions about historical delay patterns,
cancellation rates, route-level on-time performance, etc.

Time-window discipline: the tool requires both ``start_date`` and
``end_date`` as ISO ``YYYY-MM-DD`` strings. "Last month" or "last 3
months" is the LLM's job to translate into a concrete window using the
``[Today is YYYY-MM-DD]`` context the agent prompts include.
"""

from __future__ import annotations

import time
from datetime import date

from pydantic import Field
from pydantic_ai import Agent, RunContext

from aviation_copilot.agent.core import AgentDeps
from aviation_copilot.agent.errors import ToolError
from aviation_copilot.data.schema import FlightDataError, RouteQuery, RouteSummary
from aviation_copilot.tools._base import truncate_for_trace

TOOL_NAME = "flight_data_query"


def register(agent: Agent[AgentDeps, str]) -> None:
    """Register ``flight_data_query`` on the given agent.

    The decorator captures the function signature; Pydantic-AI generates a
    tool schema that includes the typed parameters, default values, and the
    ``Field(description=...)`` text below.
    """

    @agent.tool
    async def flight_data_query(
        ctx: RunContext[AgentDeps],
        origin: str = Field(
            description=(
                "Origin airport IATA code (3 letters, e.g. 'ORD') or ICAO "
                "(4 letters, e.g. 'KORD'). Must be a US top-50 airport."
            )
        ),
        dest: str = Field(description="Destination airport IATA or ICAO. US top-50 only."),
        start_date: str = Field(
            description="Inclusive start of date window, ISO format YYYY-MM-DD."
        ),
        end_date: str = Field(description="Inclusive end of date window, ISO format YYYY-MM-DD."),
        airline: str | None = Field(
            default=None,
            description="Optional IATA airline code (e.g. 'AA', 'UA').",
        ),
    ) -> RouteSummary:
        """Aggregate historical on-time performance for a route over a date window.

        Returns a summary of total flights, cancellations, on-time rate, mean
        delays, and per-cause delay minutes. Use this for questions about
        delay patterns, cancellation rates, route-level statistics.
        """
        return await _execute(
            ctx.deps,
            origin=origin,
            dest=dest,
            start_date=start_date,
            end_date=end_date,
            airline=airline,
        )


async def _execute(
    deps: AgentDeps,
    *,
    origin: str,
    dest: str,
    start_date: str,
    end_date: str,
    airline: str | None,
) -> RouteSummary:
    started = time.perf_counter()
    deps.trace.append_tool_call(
        tool_name=TOOL_NAME,
        args={
            "origin": origin,
            "dest": dest,
            "start_date": start_date,
            "end_date": end_date,
            "airline": airline,
        },
    )
    try:
        query = _build_query(
            origin=origin,
            dest=dest,
            start_date=start_date,
            end_date=end_date,
            airline=airline,
        )
    except (ValueError, TypeError) as exc:
        deps.trace.append_error(
            error_kind="tool_error:invalid_input",
            message=str(exc),
            tool_name=TOOL_NAME,
        )
        raise ToolError(
            kind="invalid_input",
            retryable=False,
            user_message=str(exc),
        ) from exc

    if deps.flight_db is None:
        deps.trace.append_error(
            error_kind="tool_error:unavailable",
            message="flight_db is not wired into AgentDeps.",
            tool_name=TOOL_NAME,
        )
        raise ToolError(
            kind="unavailable",
            retryable=False,
            user_message="The flight database is not available in this environment.",
        )

    try:
        summary = deps.flight_db.summarize_route(query)
    except FlightDataError as exc:
        deps.trace.append_error(
            error_kind="tool_error:db_error",
            message=exc.args[0] if exc.args else "DB error",
            tool_name=TOOL_NAME,
        )
        raise ToolError(
            kind="db_error",
            retryable=False,
            user_message=f"Flight database query failed: {exc.args[0] if exc.args else 'unknown'}.",
        ) from exc

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    preview = (
        f"{summary.origin}->{summary.dest}: "
        f"{summary.flights.total_flights} flights, "
        f"{summary.flights.on_time_rate:.0%} on-time, "
        f"{summary.flights.cancelled} cancelled"
    )
    deps.trace.append_tool_result(
        tool_name=TOOL_NAME,
        result_preview=truncate_for_trace(preview),
        success=True,
        latency_ms=elapsed_ms,
    )
    return summary


def _build_query(
    *,
    origin: str,
    dest: str,
    start_date: str,
    end_date: str,
    airline: str | None,
) -> RouteQuery:
    """Parse string args into a typed RouteQuery, raising ValueError on bad input."""
    try:
        start = date.fromisoformat(start_date)
    except ValueError as exc:
        raise ValueError(f"start_date must be YYYY-MM-DD; got {start_date!r}") from exc
    try:
        end = date.fromisoformat(end_date)
    except ValueError as exc:
        raise ValueError(f"end_date must be YYYY-MM-DD; got {end_date!r}") from exc
    return RouteQuery(
        origin=origin,
        dest=dest,
        start_date=start,
        end_date=end,
        airline=airline,
    )
