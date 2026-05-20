"""Tests for the notam_lookup tool."""

from __future__ import annotations

import pytest
import respx
from aviation_copilot.agent.core import AgentDeps, build_agent, clear_tool_registrars
from aviation_copilot.agent.errors import ToolError
from aviation_copilot.agent.trace import Trace
from aviation_copilot.tools import notam
from aviation_copilot.tools.notam import AWC_NOTAM_BASE, _execute
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


def _notam_payload() -> list[dict]:
    return [
        {
            "notamId": "!ORD 12/345",
            "notamText": ("RWY 10L/28R CLSD DUE TO MAINT. EXPECT DELAYS DURING PEAK HOURS."),
            "issuedDate": "2026-05-18T18:00:00Z",
            "effectiveStart": "2026-05-19T06:00:00Z",
            "effectiveEnd": "2026-05-20T06:00:00Z",
            "classification": "DOM",
        },
        {
            "notamId": "!ORD 12/346",
            "notamText": "ILS RWY 22L OTS DUE TO MAINT",
            "issuedDate": "2026-05-19T03:00:00Z",
        },
    ]


class TestInvalidInput:
    async def test_bad_icao(self, deps: AgentDeps) -> None:
        with pytest.raises(ToolError) as exc_info:
            await _execute(deps, icao="ORD")  # 3 letters
        assert exc_info.value.kind == "invalid_input"


class TestHappyPath:
    @respx.mock
    async def test_returns_active_notams(self, deps: AgentDeps) -> None:
        respx.get(f"{AWC_NOTAM_BASE}/api/data/notam").mock(
            return_value=Response(200, json=_notam_payload())
        )
        result = await _execute(deps, icao="KORD")
        assert result.icao == "KORD"
        assert len(result.notams) == 2
        assert result.notams[0].notam_id.startswith("!ORD")
        assert "RWY 10L/28R" in result.notams[0].text

    @respx.mock
    async def test_alt_text_field_name(self, deps: AgentDeps) -> None:
        # Some upstreams use "text" instead of "notamText".
        respx.get(f"{AWC_NOTAM_BASE}/api/data/notam").mock(
            return_value=Response(
                200,
                json=[{"id": "!ABC", "text": "alt-shape notam"}],
            )
        )
        result = await _execute(deps, icao="KORD")
        assert result.notams[0].text == "alt-shape notam"


class TestEmptyPath:
    @respx.mock
    async def test_no_notams_returns_friendly_note(self, deps: AgentDeps) -> None:
        respx.get(f"{AWC_NOTAM_BASE}/api/data/notam").mock(return_value=Response(200, json=[]))
        result = await _execute(deps, icao="KORD")
        assert result.notams == []
        assert any("No active NOTAMs" in n for n in result.notes)
        # Empty result is NOT an error.
        assert not deps.trace.errors()

    @respx.mock
    async def test_data_wrapped_in_object(self, deps: AgentDeps) -> None:
        # Some upstreams wrap the list under a "data" key.
        respx.get(f"{AWC_NOTAM_BASE}/api/data/notam").mock(
            return_value=Response(
                200,
                json={"data": _notam_payload()},
            )
        )
        result = await _execute(deps, icao="KORD")
        assert len(result.notams) == 2

    @respx.mock
    async def test_skips_records_without_text(self, deps: AgentDeps) -> None:
        respx.get(f"{AWC_NOTAM_BASE}/api/data/notam").mock(
            return_value=Response(
                200,
                json=[
                    {"notamId": "good", "notamText": "real notam"},
                    {"notamId": "empty", "notamText": ""},
                    {"notamId": "stringly", "extra": "no-text-field"},
                ],
            )
        )
        result = await _execute(deps, icao="KORD")
        # Only the "good" record survives.
        assert len(result.notams) == 1
        assert result.notams[0].text == "real notam"


class TestErrorPaths:
    @respx.mock
    async def test_5xx_retryable(self, deps: AgentDeps) -> None:
        respx.get(f"{AWC_NOTAM_BASE}/api/data/notam").mock(return_value=Response(503))
        with pytest.raises(ToolError) as exc_info:
            await _execute(deps, icao="KORD")
        assert exc_info.value.retryable

    @respx.mock
    async def test_4xx_non_retryable(self, deps: AgentDeps) -> None:
        respx.get(f"{AWC_NOTAM_BASE}/api/data/notam").mock(return_value=Response(404))
        with pytest.raises(ToolError) as exc_info:
            await _execute(deps, icao="KORD")
        assert not exc_info.value.retryable


class TestRegistration:
    def test_register_adds_tool_to_agent(self) -> None:
        agent: Agent[AgentDeps, str] = build_agent(model=TestModel(), apply_tool_registrars=False)
        notam.register(agent)
        tool_names = {t.name for t in agent._function_toolset.tools.values()}
        assert "notam_lookup" in tool_names
