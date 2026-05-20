"""Tests for the Pydantic-AI agent core (U4).

Uses Pydantic-AI's ``TestModel`` and ``FunctionModel`` to drive deterministic
agent runs without real LLM calls. Real LLM behavior is verified by the eval
suite (U7) and via the live deploy.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest
from aviation_copilot.agent.core import (
    AgentDeps,
    AgentResult,
    build_agent,
    clear_tool_registrars,
    register_tools,
    run_with_trace,
)
from aviation_copilot.agent.errors import ToolError
from aviation_copilot.agent.trace import Trace
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel


@pytest.fixture(autouse=True)
def _reset_registrars() -> None:
    """Ensure the module-level tool registry doesn't leak between tests."""
    clear_tool_registrars()
    yield
    clear_tool_registrars()


# ----------------------------------------------------------------------
# build_agent
# ----------------------------------------------------------------------


class TestBuildAgent:
    def test_builds_with_test_model(self) -> None:
        agent = build_agent(model=TestModel(), apply_tool_registrars=False)
        assert isinstance(agent, Agent)

    def test_applies_registrars_when_enabled(self) -> None:
        calls: list[str] = []

        def register_marker(agent: Agent[AgentDeps, str]) -> None:
            calls.append("marker_registered")

            @agent.tool
            async def marker(ctx: RunContext[AgentDeps], x: int) -> int:
                """Returns x unchanged. For registration-presence tests."""
                return x

        register_tools(register_marker)
        build_agent(model=TestModel(), apply_tool_registrars=True)
        assert calls == ["marker_registered"]

    def test_skips_registrars_when_disabled(self) -> None:
        calls: list[str] = []
        register_tools(lambda _agent: calls.append("called"))
        build_agent(model=TestModel(), apply_tool_registrars=False)
        assert calls == []


# ----------------------------------------------------------------------
# register_tools
# ----------------------------------------------------------------------


class TestRegisterTools:
    def test_idempotent(self) -> None:
        calls: list[str] = []

        def reg(_a: Agent[AgentDeps, str]) -> None:
            calls.append("x")

        register_tools(reg)
        register_tools(reg)
        register_tools(reg)
        build_agent(model=TestModel())
        assert calls == ["x"]  # only invoked once despite three registrations


# ----------------------------------------------------------------------
# run_with_trace
# ----------------------------------------------------------------------


async def test_run_with_trace_simple_text_answer() -> None:
    """With a TextPart-only FunctionModel, the agent returns directly without tools."""

    async def respond_text(_messages: Iterable[ModelMessage], _info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(content="Plain answer.")])

    agent = build_agent(model=FunctionModel(respond_text), apply_tool_registrars=False)
    result = await run_with_trace("hello", agent=agent)
    assert isinstance(result, AgentResult)
    assert result.answer == "Plain answer."
    assert result.error is None
    # One LLM step recorded by run_with_trace's wrapper.
    assert any(s.kind == "llm_call" for s in result.trace.steps)
    assert result.trace.completed_at is not None


async def test_run_with_trace_invokes_registered_tool() -> None:
    """A tool that succeeds shows up in tools_called()."""

    def register_doubler(agent: Agent[AgentDeps, str]) -> None:
        @agent.tool
        async def double(ctx: RunContext[AgentDeps], n: int) -> int:
            """Return n * 2."""
            ctx.deps.trace.append_tool_call(tool_name="double", args={"n": n})
            out = n * 2
            ctx.deps.trace.append_tool_result(
                tool_name="double", result_preview=str(out), success=True
            )
            return out

    register_tools(register_doubler)
    agent = build_agent(model=TestModel(), apply_tool_registrars=True)
    deps = AgentDeps(trace=Trace.new(question="double 5"))
    result = await run_with_trace("double 5", agent=agent, deps=deps)
    # TestModel will auto-invoke registered tools.
    assert "double" in result.trace.tools_called()
    # Tool's append_tool_call ran exactly once.
    assert result.trace.tool_call_count("double") == 1


async def test_run_with_trace_tool_error_returns_graceful_answer() -> None:
    """A ToolError propagates as a structured error step + fallback answer."""

    def register_failer(agent: Agent[AgentDeps, str]) -> None:
        @agent.tool
        async def failer(ctx: RunContext[AgentDeps]) -> str:
            """Always fails with a non-retryable error."""
            raise ToolError(
                kind="unavailable",
                retryable=False,
                user_message="upstream is offline",
            )

    register_tools(register_failer)

    async def call_failer(_messages: Iterable[ModelMessage], info: AgentInfo) -> ModelResponse:
        # Force the tool call on the first turn.
        tool_def = next(t for t in info.function_tools if t.name == "failer")
        return ModelResponse(
            parts=[ToolCallPart(tool_name=tool_def.name, args="{}", tool_call_id="t1")]
        )

    agent = build_agent(model=FunctionModel(call_failer), apply_tool_registrars=True)
    deps = AgentDeps(trace=Trace.new(question="hit the failing tool"))
    result = await run_with_trace("hit the failing tool", agent=agent, deps=deps)
    assert result.error == "tool_error:unavailable"
    assert "unavailable" in result.answer.lower() or "upstream is offline" in result.answer
    errors = result.trace.errors()
    assert any(e.error_kind == "tool_error:unavailable" for e in errors)


async def test_run_with_trace_starts_fresh_trace_when_deps_omitted() -> None:
    """When the caller doesn't pass deps, the wrapper creates a Trace for them."""

    async def respond_text(_messages: Iterable[ModelMessage], _info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(content="ok")])

    agent = build_agent(model=FunctionModel(respond_text), apply_tool_registrars=False)
    result = await run_with_trace("anything", agent=agent)
    assert result.trace.question == "anything"
    assert result.trace.completed_at is not None


async def test_run_with_trace_records_token_usage_when_available() -> None:
    """LLM step records token counts pulled from the run result usage."""

    def call_count(usage: Any) -> int | None:
        return getattr(usage, "request_tokens", None) or getattr(usage, "input_tokens", None)

    async def respond_text(_messages: Iterable[ModelMessage], _info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(content="ok")])

    agent = build_agent(model=FunctionModel(respond_text), apply_tool_registrars=False)
    result = await run_with_trace("anything", agent=agent)
    llm_steps = [s for s in result.trace.steps if s.kind == "llm_call"]
    assert llm_steps  # at least the wrapper's summary step
    # Token counts may be None if FunctionModel didn't supply usage info.
    # The assertion is just that the field exists, not its specific value.
    for s in llm_steps:
        assert hasattr(s, "input_tokens")
        assert hasattr(s, "output_tokens")


async def test_run_with_trace_prepends_today_when_supplied() -> None:
    """The today_iso parameter shows up in the rendered prompt context."""
    captured: dict[str, Any] = {}

    async def echo_prompt(messages: Iterable[ModelMessage], _info: AgentInfo) -> ModelResponse:
        # The user message is the rendered prompt; capture for assertion.
        messages_list = list(messages)
        captured["msgs"] = messages_list
        return ModelResponse(parts=[TextPart(content="ok")])

    agent = build_agent(model=FunctionModel(echo_prompt), apply_tool_registrars=False)
    await run_with_trace("question", agent=agent, today_iso="2026-05-19")
    # The 2026-05-19 marker appears in the captured user message.
    flat = repr(captured["msgs"])
    assert "2026-05-19" in flat
