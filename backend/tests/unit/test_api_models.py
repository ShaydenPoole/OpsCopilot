"""Tests for the API request / response Pydantic models."""

from __future__ import annotations

import pytest
from aviation_copilot.agent.trace import Trace
from aviation_copilot.api.models import (
    HealthResponse,
    QueryRequest,
    QueryResponse,
    SseEvent,
    VersionResponse,
)
from pydantic import ValidationError


class TestQueryRequest:
    def test_minimal(self) -> None:
        r = QueryRequest(question="What's the on-time rate?")
        assert r.question.startswith("What's")
        assert r.today_iso is None

    def test_empty_question_rejected(self) -> None:
        with pytest.raises(ValidationError):
            QueryRequest(question="")

    def test_oversize_question_rejected(self) -> None:
        with pytest.raises(ValidationError):
            QueryRequest(question="x" * 5000)


class TestSseEvent:
    def test_step_event_round_trip(self) -> None:
        trace = Trace.new()
        step = trace.append_tool_call(tool_name="weather_lookup", args={"icao": "KORD"})
        event = SseEvent(type="step", payload=step)
        payload = event.model_dump_json()
        rt = SseEvent.model_validate_json(payload)
        assert rt.type == "step"

    def test_final_event_accepts_dict_payload(self) -> None:
        ev = SseEvent(type="final", payload={"answer": "x", "trace_id": "abc"})
        rt = SseEvent.model_validate_json(ev.model_dump_json())
        assert rt.type == "final"
        assert isinstance(rt.payload, dict)

    def test_done_event_has_empty_payload(self) -> None:
        ev = SseEvent(type="done", payload={})
        assert ev.payload == {}


class TestQueryResponse:
    def test_minimal_response(self) -> None:
        t = Trace.new(question="hi")
        t.finalize()
        r = QueryResponse(trace_id=t.trace_id, answer="hi", trace=t)
        assert r.error is None
        assert r.answer == "hi"

    def test_round_trip(self) -> None:
        t = Trace.new(question="round-trip me")
        t.append_tool_call(tool_name="x", args={})
        t.finalize()
        r = QueryResponse(trace_id=t.trace_id, answer="ok", trace=t, error=None)
        rt = QueryResponse.model_validate_json(r.model_dump_json())
        assert rt.trace_id == t.trace_id
        assert len(rt.trace.steps) == 1


class TestHealthAndVersion:
    def test_health_minimal(self) -> None:
        h = HealthResponse(status="ok", flight_db_ready=True, corpus_index_ready=True)
        assert h.status == "ok"
        assert h.notes == []

    def test_version_minimal(self) -> None:
        v = VersionResponse(
            version="0.1.0",
            agent_model="openai/gpt-oss-120b",
            judge_model="meta-llama/llama-3.3-70b-instruct",
        )
        assert v.name == "aviation-ops-copilot"
        assert v.git_sha is None
