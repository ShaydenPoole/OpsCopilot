"""End-to-end agent-service integration tests (U10).

Drives the real FastAPI app, agent loop, and tool code through the `/query`
SSE endpoint. The LLM is a scripted ``FunctionModel`` cassette and upstream
HTTP is mocked with ``respx`` — see ``cassettes/README.md``.

Coverage:
- A multi-tool run (weather + NOTAM) — AE1: the agent calls multiple typed
  tools and the trace records each call.
- A forced tool failure — AE2 / R3: a tool error degrades gracefully into a
  non-fabricated answer instead of a 502 or an invented NOTAM.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from aviation_copilot.agent.core import build_agent, clear_tool_registrars
from aviation_copilot.api.app import create_app
from aviation_copilot.api.rate_limit import DailyBudget, RateLimiter
from aviation_copilot.config import Settings
from aviation_copilot.tools import register_default_registrars
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

pytestmark = pytest.mark.integration

AWC = "https://aviationweather.gov"


# ----------------------------------------------------------------------
# Cassettes — scripted FunctionModel conversations
# ----------------------------------------------------------------------


def _count_tool_returns(messages: list[ModelMessage]) -> int:
    """How many tool results the agent has received so far this run."""
    return sum(
        1
        for message in messages
        for part in getattr(message, "parts", [])
        if type(part).__name__ == "ToolReturnPart"
    )


def _weather_then_notam(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
    """Cassette: call weather_lookup, then notam_lookup, then answer."""
    turn = _count_tool_returns(messages)
    if turn == 0:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="weather_lookup",
                    args={"icao": "KORD", "product": "metar"},
                    tool_call_id="call-weather",
                )
            ]
        )
    if turn == 1:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="notam_lookup",
                    args={"icao": "KORD"},
                    tool_call_id="call-notam",
                )
            ]
        )
    return ModelResponse(
        parts=[
            TextPart(
                content=(
                    "KORD is currently VFR. One NOTAM is active for a taxiway "
                    "closure. Sources: weather_lookup, notam_lookup."
                )
            )
        ]
    )


def _call_notam_once(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
    """Cassette: call notam_lookup once. The tool fails before a second turn."""
    if _count_tool_returns(messages) == 0:
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="notam_lookup",
                    args={"icao": "KORD"},
                    tool_call_id="call-notam",
                )
            ]
        )
    return ModelResponse(parts=[TextPart(content="(unreachable in this cassette)")])


# ----------------------------------------------------------------------
# Upstream payloads
# ----------------------------------------------------------------------


def _metar_payload() -> list[dict[str, Any]]:
    return [
        {
            "icaoId": "KORD",
            "rawOb": "KORD 191651Z 36008KT 10SM FEW250 15/04 A3001",
            "obsTime": int(time.time()),  # fresh — not stale
            "fltCat": "VFR",
            "wspd": 8,
            "visib": 10,
            "temp": 15,
        }
    ]


def _notam_payload() -> list[dict[str, Any]]:
    return [
        {
            "notamId": "ORD 05/123",
            "notamText": "TWY B CLSD BTN TWY C AND TWY D",
            "classification": "DOM",
        }
    ]


# ----------------------------------------------------------------------
# App builder
# ----------------------------------------------------------------------


def _build_client(model: FunctionModel) -> Iterator[TestClient]:
    clear_tool_registrars()
    register_default_registrars()
    settings = Settings(test_mode=True)
    agent = build_agent(model=model, settings=settings, apply_tool_registrars=True)
    app = create_app(
        settings=settings,
        agent=agent,
        rate_limiter=RateLimiter(rate_per_second=100.0, burst=100.0),
        daily_budget=DailyBudget(max_tokens_per_day=10_000_000),
    )
    with TestClient(app) as client:
        yield client
    clear_tool_registrars()


def _parse_sse(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
    return events


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------


class TestMultiToolRun:
    """AE1 — the agent orchestrates multiple typed tools in one answer."""

    @respx.mock
    def test_weather_and_notam_both_appear_in_the_trace(self) -> None:
        respx.get(url__regex=r".*/api/data/metar.*").mock(
            return_value=httpx.Response(200, json=_metar_payload())
        )
        respx.get(url__regex=r".*/api/data/notam.*").mock(
            return_value=httpx.Response(200, json=_notam_payload())
        )

        client = next(_build_client(FunctionModel(_weather_then_notam)))
        try:
            response = client.post("/query", json={"question": "Weather and NOTAMs at KORD?"})
            assert response.status_code == 200

            events = _parse_sse(response.text)
            finals = [e for e in events if e["type"] == "final"]
            assert len(finals) == 1
            assert any(e["type"] == "done" for e in events)

            final = finals[0]["payload"]
            assert final["error"] is None
            assert "VFR" in final["answer"]

            # Both tools are recorded in the structured trace.
            tool_calls = [
                step["tool_name"] for step in final["trace"]["steps"] if step["kind"] == "tool_call"
            ]
            assert "weather_lookup" in tool_calls
            assert "notam_lookup" in tool_calls

            # The persisted trace is retrievable by id.
            trace_resp = client.get(f"/trace/{final['trace_id']}")
            assert trace_resp.status_code == 200
            assert trace_resp.json()["trace_id"] == final["trace_id"]
        finally:
            client.close()


class TestGracefulToolFailure:
    """AE2 / R3 — a tool failure degrades into a safe, non-fabricated answer."""

    @respx.mock
    def test_notam_failure_yields_non_fabricated_answer(self) -> None:
        # The NOTAM upstream rejects the request — a non-retryable client error.
        respx.get(url__regex=r".*/api/data/notam.*").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )

        client = next(_build_client(FunctionModel(_call_notam_once)))
        try:
            response = client.post("/query", json={"question": "Any current NOTAMs for KORD?"})
            # The stream still completes cleanly — no 502, no hang.
            assert response.status_code == 200

            events = _parse_sse(response.text)
            finals = [e for e in events if e["type"] == "final"]
            assert len(finals) == 1
            assert any(e["type"] == "done" for e in events)

            final = finals[0]["payload"]
            # The run is flagged with the structured error kind.
            assert final["error"] == "tool_error:upstream_client_error"

            # The answer acknowledges the gap rather than inventing a NOTAM.
            answer = final["answer"].lower()
            assert "couldn't complete" in answer or "unavailable" in answer
            assert "twy b clsd" not in answer  # the (unseen) upstream NOTAM text

            # The trace records the failed tool call + the error step.
            steps = final["trace"]["steps"]
            assert any(s["kind"] == "tool_call" and s["tool_name"] == "notam_lookup" for s in steps)
            assert any(s["kind"] == "error" for s in steps)
        finally:
            client.close()
