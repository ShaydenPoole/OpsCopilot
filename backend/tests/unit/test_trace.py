"""Tests for the Trace model.

The trace is the contract between the agent and three downstream consumers
(UI, eval scorers, Langfuse). These tests pin its append behavior, JSON
round-trip, and the accessor methods scorers will call.
"""

from __future__ import annotations

import json
from datetime import datetime

from aviation_copilot.agent.trace import (
    ErrorStep,
    LLMCallStep,
    ToolCallStep,
    ToolResultStep,
    Trace,
)


class TestTraceBasics:
    def test_new_trace_has_no_steps(self) -> None:
        t = Trace.new(question="What's the on-time rate for ORD->LGA?")
        assert t.steps == []
        assert t.question.startswith("What's")
        assert t.completed_at is None
        assert isinstance(t.started_at, datetime)

    def test_append_llm(self) -> None:
        t = Trace.new()
        step = t.append_llm(
            model="openai/gpt-oss-120b",
            input_tokens=400,
            output_tokens=200,
            cost_usd=0.0015,
            latency_ms=820.0,
        )
        assert isinstance(step, LLMCallStep)
        assert t.steps[-1] is step
        assert step.model == "openai/gpt-oss-120b"

    def test_append_tool_call_and_result(self) -> None:
        t = Trace.new()
        call = t.append_tool_call(tool_name="weather_lookup", args={"icao": "KORD"})
        result = t.append_tool_result(
            tool_name="weather_lookup",
            result_preview="METAR KORD 010053Z ...",
            success=True,
            latency_ms=180.0,
        )
        assert isinstance(call, ToolCallStep)
        assert isinstance(result, ToolResultStep)
        assert len(t.steps) == 2

    def test_append_error(self) -> None:
        t = Trace.new()
        step = t.append_error(
            error_kind="tool_error:upstream_timeout",
            message="NOAA timed out",
            retryable=True,
            tool_name="weather_lookup",
        )
        assert isinstance(step, ErrorStep)
        assert step.retryable
        assert step.tool_name == "weather_lookup"

    def test_finalize_sets_completed(self) -> None:
        t = Trace.new()
        t.finalize()
        assert t.completed_at is not None
        # Calling finalize twice does not overwrite the first timestamp.
        first = t.completed_at
        t.finalize()
        assert t.completed_at == first


class TestTraceJsonRoundTrip:
    def test_round_trip_preserves_steps(self) -> None:
        t = Trace.new(question="Why is ORD delayed?")
        t.append_tool_call(tool_name="flight_data_query", args={"origin": "ORD"})
        t.append_tool_result(
            tool_name="flight_data_query", result_preview="60 flights, ~30% on-time"
        )
        t.append_llm(model="m", input_tokens=120, output_tokens=80, cost_usd=0.001, latency_ms=750)
        t.finalize()

        payload = t.model_dump_json()
        rt = Trace.model_validate_json(payload)
        assert rt.question == "Why is ORD delayed?"
        assert len(rt.steps) == 3
        assert rt.steps[0].kind == "tool_call"
        assert rt.steps[1].kind == "tool_result"
        assert rt.steps[2].kind == "llm_call"
        assert isinstance(rt.steps[2], LLMCallStep)
        assert rt.steps[2].cost_usd == 0.001

    def test_json_uses_discriminator(self) -> None:
        t = Trace.new()
        t.append_tool_call(tool_name="x", args={"a": 1})
        payload = json.loads(t.model_dump_json())
        assert payload["steps"][0]["kind"] == "tool_call"


class TestTraceAccessors:
    def _trace_with_mixed_steps(self) -> Trace:
        t = Trace.new(question="multi-tool question")
        t.append_tool_call(tool_name="flight_data_query", args={})
        t.append_tool_result(tool_name="flight_data_query", result_preview="...")
        t.append_tool_call(tool_name="weather_lookup", args={"icao": "KORD"})
        t.append_tool_result(tool_name="weather_lookup", result_preview="...")
        t.append_tool_call(tool_name="flight_data_query", args={"origin": "ORD"})
        t.append_tool_result(tool_name="flight_data_query", result_preview="...")
        t.append_llm(model="m", input_tokens=300, output_tokens=150, cost_usd=0.002)
        t.append_llm(model="m", input_tokens=100, output_tokens=50, cost_usd=0.001)
        t.append_error(error_kind="tool_error:db_error", message="x")
        return t

    def test_tools_called_returns_unique_in_order(self) -> None:
        t = self._trace_with_mixed_steps()
        assert t.tools_called() == ["flight_data_query", "weather_lookup"]

    def test_tool_call_count_total(self) -> None:
        t = self._trace_with_mixed_steps()
        assert t.tool_call_count() == 3

    def test_tool_call_count_by_name(self) -> None:
        t = self._trace_with_mixed_steps()
        assert t.tool_call_count("flight_data_query") == 2
        assert t.tool_call_count("weather_lookup") == 1
        assert t.tool_call_count("nonexistent") == 0

    def test_errors_filter(self) -> None:
        t = self._trace_with_mixed_steps()
        errors = t.errors()
        assert len(errors) == 1
        assert errors[0].error_kind == "tool_error:db_error"

    def test_cost_and_token_totals(self) -> None:
        t = self._trace_with_mixed_steps()
        assert t.total_cost_usd() == 0.003
        assert t.total_input_tokens() == 400
        assert t.total_output_tokens() == 200

    def test_cost_totals_with_no_llm_calls(self) -> None:
        t = Trace.new()
        assert t.total_cost_usd() == 0.0
        assert t.total_input_tokens() == 0
        assert t.total_output_tokens() == 0
