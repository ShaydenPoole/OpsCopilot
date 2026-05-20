"""Tests for Langfuse observability (U8).

The Langfuse client is duck-typed (see :class:`LangfuseObserver`), so these
tests inject a :class:`FakeLangfuseClient` that records every observation
instead of talking to Langfuse Cloud. Real export is verified manually at
deploy time — see ``docs/deploy.md`` (U11).
"""

from __future__ import annotations

from typing import Any

import pytest
from aviation_copilot.agent.core import AgentResult, build_agent, run_with_trace
from aviation_copilot.agent.trace import Trace
from aviation_copilot.config import Settings
from aviation_copilot.observability import (
    AgentObserver,
    LangfuseObserver,
    NoopObserver,
    build_observer,
)
from pydantic_ai.models.test import TestModel

# ----------------------------------------------------------------------
# Fake Langfuse client
# ----------------------------------------------------------------------


class FakeObservation:
    """Records every call made against one Langfuse observation."""

    def __init__(self, kwargs: dict[str, Any]) -> None:
        self.kwargs = kwargs
        self.children: list[FakeObservation] = []
        self.updates: list[dict[str, Any]] = []
        self.ended = False
        self.trace_id = "otel-trace-id"

    def start_observation(self, **kwargs: Any) -> FakeObservation:
        child = FakeObservation(kwargs)
        self.children.append(child)
        return child

    def update(self, **kwargs: Any) -> FakeObservation:
        self.updates.append(kwargs)
        return self

    def end(self, **kwargs: Any) -> FakeObservation:
        self.ended = True
        return self


class FakeLangfuseClient:
    """A stand-in for the Langfuse v4 client. No network, fully inspectable."""

    def __init__(self) -> None:
        self.roots: list[FakeObservation] = []
        self.flushed = 0

    def start_observation(self, **kwargs: Any) -> FakeObservation:
        root = FakeObservation(kwargs)
        self.roots.append(root)
        return root

    def flush(self) -> None:
        self.flushed += 1

    def get_trace_url(self, *, trace_id: str | None = None) -> str | None:
        return f"https://cloud.langfuse.com/trace/{trace_id}"


# ----------------------------------------------------------------------
# Trace builders
# ----------------------------------------------------------------------


def _single_tool_trace() -> Trace:
    """A trace with one successful tool call + one LLM summary call."""
    trace = Trace.new(question="What is the weather at KORD?")
    trace.append_tool_call(tool_name="weather_lookup", args={"icao": "KORD"})
    trace.append_tool_result(
        tool_name="weather_lookup",
        result_preview="VFR, wind 8kt, vis 10sm",
        success=True,
        latency_ms=120.0,
    )
    trace.append_llm(
        model="openai/gpt-oss-120b",
        input_tokens=900,
        output_tokens=120,
        cost_usd=0.00041,
        latency_ms=850.0,
    )
    trace.finalize()
    return trace


def _result(trace: Trace, *, answer: str = "Answer.", error: str | None = None) -> AgentResult:
    return AgentResult(answer=answer, trace=trace, error=error)


# ----------------------------------------------------------------------
# LangfuseObserver.record_run — happy path
# ----------------------------------------------------------------------


class TestRecordRun:
    def test_creates_one_root_with_a_child_per_step(self) -> None:
        client = FakeLangfuseClient()
        url = LangfuseObserver(client).record_run(_result(_single_tool_trace()))

        assert len(client.roots) == 1
        root = client.roots[0]
        assert root.kwargs["as_type"] == "agent"
        assert root.kwargs["input"] == {"question": "What is the weather at KORD?"}
        assert root.ended is True
        # One tool span (call + result paired) and one generation.
        assert len(root.children) == 2
        kinds = sorted(c.kwargs["as_type"] for c in root.children)
        assert kinds == ["generation", "tool"]
        assert all(c.ended for c in root.children)
        assert url == "https://cloud.langfuse.com/trace/otel-trace-id"

    def test_llm_generation_carries_cost_and_token_usage(self) -> None:
        client = FakeLangfuseClient()
        LangfuseObserver(client).record_run(_result(_single_tool_trace()))

        gen = next(c for c in client.roots[0].children if c.kwargs["as_type"] == "generation")
        assert gen.kwargs["model"] == "openai/gpt-oss-120b"
        assert gen.kwargs["cost_details"] == {"total": 0.00041}
        assert gen.kwargs["usage_details"] == {"input": 900, "output": 120}

    def test_tool_span_carries_input_args_and_output(self) -> None:
        client = FakeLangfuseClient()
        LangfuseObserver(client).record_run(_result(_single_tool_trace()))

        tool = next(c for c in client.roots[0].children if c.kwargs["as_type"] == "tool")
        assert tool.kwargs["name"] == "tool.weather_lookup"
        assert tool.kwargs["input"] == {"icao": "KORD"}
        assert tool.kwargs["output"] == "VFR, wind 8kt, vis 10sm"
        assert tool.kwargs["level"] == "DEFAULT"
        assert tool.kwargs["metadata"]["success"] is True

    def test_root_records_answer_and_default_level_on_success(self) -> None:
        client = FakeLangfuseClient()
        LangfuseObserver(client).record_run(_result(_single_tool_trace(), answer="It is VFR."))

        update = client.roots[0].updates[-1]
        assert update["output"] == {"answer": "It is VFR."}
        assert update["level"] == "DEFAULT"
        assert update["status_message"] is None

    def test_llm_only_trace_emits_a_single_generation(self) -> None:
        """An agent run with no tool calls produces one generation child."""
        trace = Trace.new(question="hello")
        trace.append_llm(model="openai/gpt-oss-120b", input_tokens=10, output_tokens=5)
        trace.finalize()

        client = FakeLangfuseClient()
        LangfuseObserver(client).record_run(_result(trace))

        children = client.roots[0].children
        assert len(children) == 1
        assert children[0].kwargs["as_type"] == "generation"


# ----------------------------------------------------------------------
# Error handling
# ----------------------------------------------------------------------


class TestRecordRunErrors:
    def test_failed_tool_span_is_marked_error(self) -> None:
        """A tool that raises mid-execution → its span closes with ERROR level."""
        trace = Trace.new(question="Any NOTAMs for KORD?")
        trace.append_tool_call(tool_name="notam_lookup", args={"icao": "KORD"})
        trace.append_error(
            error_kind="tool_error:upstream_client_error",
            message="upstream returned HTTP 404",
            tool_name="notam_lookup",
        )
        trace.finalize()

        client = FakeLangfuseClient()
        LangfuseObserver(client).record_run(
            _result(trace, error="tool_error:upstream_client_error")
        )

        root = client.roots[0]
        tool = root.children[0]
        assert tool.kwargs["as_type"] == "tool"
        assert tool.kwargs["level"] == "ERROR"
        assert tool.kwargs["status_message"] == "upstream returned HTTP 404"
        assert tool.kwargs["metadata"]["success"] is False
        assert tool.ended is True
        # The root reflects the run-level error too.
        assert root.updates[-1]["level"] == "ERROR"
        assert root.updates[-1]["status_message"] == "tool_error:upstream_client_error"

    def test_top_level_error_emits_standalone_error_span(self) -> None:
        """A run-level error (no tool_name) emits its own ERROR span."""
        trace = Trace.new(question="...")
        trace.append_error(error_kind="max_steps_exceeded", message="hit step cap")
        trace.finalize()

        client = FakeLangfuseClient()
        LangfuseObserver(client).record_run(_result(trace, error="max_steps_exceeded"))

        children = client.roots[0].children
        assert len(children) == 1
        assert children[0].kwargs["name"] == "error.max_steps_exceeded"
        assert children[0].kwargs["level"] == "ERROR"

    def test_record_run_is_resilient_to_client_failure(self) -> None:
        """A broken Langfuse client must not surface as an agent failure."""

        class BoomClient:
            def start_observation(self, **kwargs: Any) -> Any:
                raise RuntimeError("langfuse unreachable")

        observer = LangfuseObserver(BoomClient())
        assert observer.record_run(_result(_single_tool_trace())) is None

    def test_record_run_survives_a_failure_mid_export(self) -> None:
        """If a child observation raises, the root is still ended."""

        class HalfBrokenObservation(FakeObservation):
            def start_observation(self, **kwargs: Any) -> FakeObservation:
                raise RuntimeError("export dropped")

        class HalfBrokenClient(FakeLangfuseClient):
            def start_observation(self, **kwargs: Any) -> FakeObservation:
                root = HalfBrokenObservation(kwargs)
                self.roots.append(root)
                return root

        client = HalfBrokenClient()
        # Returns None rather than raising; the root was still ended in `finally`.
        assert LangfuseObserver(client).record_run(_result(_single_tool_trace())) is None
        assert client.roots[0].ended is True


# ----------------------------------------------------------------------
# flush
# ----------------------------------------------------------------------


class TestFlush:
    def test_flush_delegates_to_client(self) -> None:
        client = FakeLangfuseClient()
        LangfuseObserver(client).flush()
        assert client.flushed == 1

    def test_flush_is_safe_when_client_raises(self) -> None:
        class BoomClient:
            def flush(self) -> None:
                raise RuntimeError("flush failed")

        LangfuseObserver(BoomClient()).flush()  # must not raise


# ----------------------------------------------------------------------
# NoopObserver
# ----------------------------------------------------------------------


class TestNoopObserver:
    def test_is_disabled_and_records_nothing(self) -> None:
        obs = NoopObserver()
        assert obs.enabled is False
        assert obs.record_run(_result(_single_tool_trace())) is None

    def test_flush_is_a_safe_noop(self) -> None:
        NoopObserver().flush()  # must not raise


# ----------------------------------------------------------------------
# build_observer factory
# ----------------------------------------------------------------------


class TestBuildObserver:
    def test_returns_noop_in_test_mode(self) -> None:
        # The autouse _isolate_env fixture sets test mode for the whole suite.
        s = Settings(test_mode=True, langfuse_public_key="pk", langfuse_secret_key="sk")
        assert isinstance(build_observer(s), NoopObserver)

    def test_returns_noop_without_credentials(self) -> None:
        s = Settings(test_mode=False, langfuse_public_key="", langfuse_secret_key="")
        observer = build_observer(s)
        assert isinstance(observer, NoopObserver)
        assert observer.enabled is False

    def test_returns_langfuse_observer_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import langfuse

        monkeypatch.setattr(langfuse, "Langfuse", lambda **kwargs: FakeLangfuseClient())
        s = Settings(test_mode=False, langfuse_public_key="pk", langfuse_secret_key="sk")
        observer = build_observer(s)
        assert isinstance(observer, LangfuseObserver)
        assert observer.enabled is True

    def test_falls_back_to_noop_when_client_init_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import langfuse

        def boom(**kwargs: Any) -> Any:
            raise RuntimeError("invalid credentials")

        monkeypatch.setattr(langfuse, "Langfuse", boom)
        s = Settings(test_mode=False, langfuse_public_key="pk", langfuse_secret_key="sk")
        assert isinstance(build_observer(s), NoopObserver)


# ----------------------------------------------------------------------
# Wiring: run_with_trace exports through the observer
# ----------------------------------------------------------------------


@pytest.mark.integration
class TestRunWithTraceWiring:
    async def test_run_with_trace_exports_to_injected_observer(self) -> None:
        """An end-to-end run (offline TestModel) reaches the observer."""
        client = FakeLangfuseClient()
        observer: AgentObserver = LangfuseObserver(client)
        agent = build_agent(model=TestModel(), apply_tool_registrars=False)

        result = await run_with_trace("hello there", agent=agent, observer=observer)

        assert result.error is None
        assert len(client.roots) == 1
        assert client.roots[0].ended is True

    async def test_run_with_trace_works_with_noop_observer(self) -> None:
        """With observability disabled the agent still runs normally."""
        agent = build_agent(model=TestModel(), apply_tool_registrars=False)
        result = await run_with_trace("hello", agent=agent, observer=NoopObserver())
        assert result.error is None
        assert result.answer
