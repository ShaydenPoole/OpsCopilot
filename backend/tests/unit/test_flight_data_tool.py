"""Tests for the flight_data_query tool."""

from __future__ import annotations

from pathlib import Path

import pytest
from aviation_copilot.agent.core import AgentDeps, build_agent, clear_tool_registrars
from aviation_copilot.agent.errors import ToolError
from aviation_copilot.agent.trace import Trace
from aviation_copilot.data.duckdb_client import DuckDBClient
from aviation_copilot.tools import flight_data
from aviation_copilot.tools.flight_data import _build_query, _execute
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from tests.fixtures.duckdb_fixture import build_test_duckdb


@pytest.fixture(scope="module")
def fixture_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_test_duckdb(tmp_path_factory.mktemp("flightdata") / "flights.duckdb")


@pytest.fixture
def deps(fixture_db: Path) -> AgentDeps:
    client = DuckDBClient(fixture_db, read_only=True)
    client.connect()
    yield AgentDeps(trace=Trace.new(), flight_db=client)
    client.close()


@pytest.fixture(autouse=True)
def _reset_registrars() -> None:
    clear_tool_registrars()
    yield
    clear_tool_registrars()


class TestBuildQuery:
    def test_parses_valid_dates(self) -> None:
        q = _build_query(
            origin="ORD",
            dest="LGA",
            start_date="2024-07-01",
            end_date="2024-07-31",
            airline=None,
        )
        assert q.origin == "ORD"
        assert q.dest == "LGA"
        assert q.start_date.isoformat() == "2024-07-01"

    def test_invalid_start_date_raises(self) -> None:
        with pytest.raises(ValueError, match="start_date"):
            _build_query(
                origin="ORD",
                dest="LGA",
                start_date="not-a-date",
                end_date="2024-07-31",
                airline=None,
            )

    def test_invalid_end_date_raises(self) -> None:
        with pytest.raises(ValueError, match="end_date"):
            _build_query(
                origin="ORD", dest="LGA", start_date="2024-07-01", end_date="July 31", airline=None
            )


class TestExecute:
    async def test_happy_path(self, deps: AgentDeps) -> None:
        summary = await _execute(
            deps,
            origin="ORD",
            dest="LGA",
            start_date="2024-07-01",
            end_date="2024-07-31",
            airline=None,
        )
        assert summary.flights.total_flights == 90
        assert deps.trace.tool_call_count("flight_data_query") == 1
        # One ToolCall + one ToolResult, no errors.
        assert not deps.trace.errors()

    async def test_no_flights_returns_zero_summary(self, deps: AgentDeps) -> None:
        summary = await _execute(
            deps,
            origin="XYZ",
            dest="ABC",
            start_date="2024-07-01",
            end_date="2024-07-31",
            airline=None,
        )
        assert summary.flights.total_flights == 0
        # Empty result is NOT an error — it's a valid no-data response.
        assert not deps.trace.errors()

    async def test_invalid_date_raises_toolerror_and_records(self, deps: AgentDeps) -> None:
        with pytest.raises(ToolError) as exc_info:
            await _execute(
                deps,
                origin="ORD",
                dest="LGA",
                start_date="garbage",
                end_date="2024-07-31",
                airline=None,
            )
        assert exc_info.value.kind == "invalid_input"
        assert not exc_info.value.retryable
        # Error step was appended.
        assert any(e.error_kind == "tool_error:invalid_input" for e in deps.trace.errors())

    async def test_missing_db_raises_toolerror(self) -> None:
        empty_deps = AgentDeps(trace=Trace.new(), flight_db=None)
        with pytest.raises(ToolError) as exc_info:
            await _execute(
                empty_deps,
                origin="ORD",
                dest="LGA",
                start_date="2024-07-01",
                end_date="2024-07-31",
                airline=None,
            )
        assert exc_info.value.kind == "unavailable"


class TestRegistration:
    def test_register_adds_tool_to_agent(self) -> None:
        agent: Agent[AgentDeps, str] = build_agent(model=TestModel(), apply_tool_registrars=False)
        flight_data.register(agent)
        # Pydantic-AI exposes registered tools on the agent's tool manager.
        tool_names = {t.name for t in agent._function_toolset.tools.values()}
        assert "flight_data_query" in tool_names
