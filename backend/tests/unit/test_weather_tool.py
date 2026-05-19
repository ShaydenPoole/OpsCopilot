"""Tests for the weather_lookup tool.

Uses ``respx`` to mock httpx calls so tests are deterministic and don't
hit the live NOAA service.
"""

from __future__ import annotations

import time

import pytest
import respx
from aviation_copilot.agent.core import AgentDeps, build_agent, clear_tool_registrars
from aviation_copilot.agent.errors import ToolError
from aviation_copilot.agent.trace import Trace
from aviation_copilot.tools import weather
from aviation_copilot.tools.weather import AWC_BASE_URL, _execute
from httpx import Response
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel


@pytest.fixture
def deps() -> AgentDeps:
    return AgentDeps(trace=Trace.new())


@pytest.fixture(autouse=True)
def _reset_registrars() -> None:
    clear_tool_registrars()
    yield
    clear_tool_registrars()


def _metar_payload() -> list[dict]:
    """Fresh-ish METAR record. obsTime = now to avoid 'stale'."""
    return [
        {
            "icaoId": "KORD",
            "rawOb": "KORD 010053Z 18012KT 10SM SCT250 21/14 A3010 RMK AO2",
            "obsTime": int(time.time()),
            "wspd": 12,
            "visib": 10,
            "temp": 21,
            "fltCat": "VFR",
        }
    ]


def _taf_payload() -> list[dict]:
    return [
        {
            "icaoId": "KORD",
            "rawTaf": "TAF KORD 011120Z 0112/0218 20012KT P6SM SCT250",
            "issueTime": "2026-05-19T11:20:00Z",
        }
    ]


class TestInvalidInput:
    async def test_bad_icao_raises_invalid_input(self, deps: AgentDeps) -> None:
        with pytest.raises(ToolError) as exc_info:
            await _execute(deps, icao="OR", product="metar")
        assert exc_info.value.kind == "invalid_input"

    async def test_numeric_icao_raises(self, deps: AgentDeps) -> None:
        with pytest.raises(ToolError) as exc_info:
            await _execute(deps, icao="1234", product="metar")
        assert exc_info.value.kind == "invalid_input"


class TestHappyPath:
    @respx.mock
    async def test_metar_only(self, deps: AgentDeps) -> None:
        respx.get(f"{AWC_BASE_URL}/api/data/metar").mock(
            return_value=Response(200, json=_metar_payload())
        )
        result = await _execute(deps, icao="KORD", product="metar")
        assert result.icao == "KORD"
        assert len(result.reports) == 1
        assert result.reports[0].product == "METAR"
        assert "VFR" in result.reports[0].summary or "wind" in result.reports[0].summary
        assert not result.reports[0].stale  # fresh obsTime

    @respx.mock
    async def test_taf_only(self, deps: AgentDeps) -> None:
        respx.get(f"{AWC_BASE_URL}/api/data/taf").mock(
            return_value=Response(200, json=_taf_payload())
        )
        result = await _execute(deps, icao="KORD", product="taf")
        assert len(result.reports) == 1
        assert result.reports[0].product == "TAF"
        assert "TAF KORD" in result.reports[0].raw_text

    @respx.mock
    async def test_both_products(self, deps: AgentDeps) -> None:
        respx.get(f"{AWC_BASE_URL}/api/data/metar").mock(
            return_value=Response(200, json=_metar_payload())
        )
        respx.get(f"{AWC_BASE_URL}/api/data/taf").mock(
            return_value=Response(200, json=_taf_payload())
        )
        result = await _execute(deps, icao="KORD", product="both")
        assert len(result.reports) == 2
        products = {r.product for r in result.reports}
        assert products == {"METAR", "TAF"}

    @respx.mock
    async def test_stale_metar_flagged(self, deps: AgentDeps) -> None:
        stale = _metar_payload()
        stale[0]["obsTime"] = int(time.time()) - 4 * 3600  # 4h old
        respx.get(f"{AWC_BASE_URL}/api/data/metar").mock(return_value=Response(200, json=stale))
        result = await _execute(deps, icao="KORD", product="metar")
        assert result.reports[0].stale


class TestEmptyAndErrorPaths:
    @respx.mock
    async def test_empty_payload_returns_notes(self, deps: AgentDeps) -> None:
        respx.get(f"{AWC_BASE_URL}/api/data/metar").mock(return_value=Response(200, json=[]))
        result = await _execute(deps, icao="KORD", product="metar")
        assert result.reports == []
        assert any("No METAR" in n for n in result.notes)

    @respx.mock
    async def test_4xx_raises_non_retryable(self, deps: AgentDeps) -> None:
        respx.get(f"{AWC_BASE_URL}/api/data/metar").mock(
            return_value=Response(400, json={"error": "bad request"})
        )
        with pytest.raises(ToolError) as exc_info:
            await _execute(deps, icao="KORD", product="metar")
        assert exc_info.value.kind == "upstream_client_error"
        assert not exc_info.value.retryable

    @respx.mock
    async def test_5xx_raises_retryable(self, deps: AgentDeps) -> None:
        respx.get(f"{AWC_BASE_URL}/api/data/metar").mock(
            return_value=Response(503, text="service unavailable")
        )
        with pytest.raises(ToolError) as exc_info:
            await _execute(deps, icao="KORD", product="metar")
        assert exc_info.value.kind == "upstream_server_error"
        assert exc_info.value.retryable

    @respx.mock
    async def test_trace_records_tool_call_and_result(self, deps: AgentDeps) -> None:
        respx.get(f"{AWC_BASE_URL}/api/data/metar").mock(
            return_value=Response(200, json=_metar_payload())
        )
        await _execute(deps, icao="KORD", product="metar")
        assert deps.trace.tool_call_count("weather_lookup") == 1
        # Result preview was appended.
        previews = [
            s
            for s in deps.trace.steps
            if s.kind == "tool_result" and s.tool_name == "weather_lookup"
        ]
        assert len(previews) == 1


class TestRegistration:
    def test_register_adds_tool_to_agent(self) -> None:
        agent: Agent[AgentDeps, str] = build_agent(model=TestModel(), apply_tool_registrars=False)
        weather.register(agent)
        tool_names = {t.name for t in agent._function_toolset.tools.values()}
        assert "weather_lookup" in tool_names
