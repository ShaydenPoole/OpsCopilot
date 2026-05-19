"""Pydantic-AI agent orchestration.

The :func:`build_agent` factory returns a configured ``Agent`` instance with
the system prompt, an OpenRouter-backed model, and registered tools. The
:func:`run_with_trace` wrapper executes a question end-to-end while capturing
a structured :class:`~aviation_copilot.agent.trace.Trace`.

Tool implementations live in :mod:`aviation_copilot.tools` (U5). U4 only
defines the registration shape — :func:`register_tools` is the seam.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from aviation_copilot.agent.errors import AgentError, MaxStepsExceededError, ToolError
from aviation_copilot.agent.prompts import AVIATION_OPS_SYSTEM_PROMPT, render_question_with_context
from aviation_copilot.agent.trace import Trace
from aviation_copilot.config import Settings, get_settings

if TYPE_CHECKING:
    from aviation_copilot.corpus.index import CorpusIndex
    from aviation_copilot.data.duckdb_client import DuckDBClient


# ----------------------------------------------------------------------
# Dependency container
# ----------------------------------------------------------------------


@dataclass
class AgentDeps:
    """Passed to every tool invocation. Holds shared clients and the trace.

    Tools mutate ``trace`` via ``trace.append_tool_call / append_tool_result``
    before and after their work, so the trace ends up complete regardless of
    whether the tool succeeded.
    """

    trace: Trace
    flight_db: DuckDBClient | None = None
    corpus_index: CorpusIndex | None = None
    # Free-form extras for things like the HTTP client used by weather/notam tools.
    extras: dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------
# Run result
# ----------------------------------------------------------------------


class AgentResult(BaseModel):
    """End-to-end result of one agent invocation."""

    answer: str
    trace: Trace
    error: str | None = None
    """``None`` on a normal completion; an error kind string when the agent
    returned a graceful partial answer due to an internal failure."""


# ----------------------------------------------------------------------
# Tool registration seam
# ----------------------------------------------------------------------


ToolRegistrar = Callable[[Agent[AgentDeps, str]], None]
"""A function that registers one or more tools on an Agent instance.

U5's tool modules export functions matching this shape so app startup can
loop over them: ``for register in tool_registrars: register(agent)``.
"""

# Registry of tool-registration callbacks. Mutated by U5's ``tools/__init__.py``
# at import time, or directly by tests that want to inject a mock tool.
_REGISTRARS: list[ToolRegistrar] = []


def register_tools(*registrars: ToolRegistrar) -> None:
    """Register one or more tool registrars.

    Idempotent: registering the same registrar twice is a no-op. Tests use
    this to add stub tools without modifying the production tool registry.
    """
    for r in registrars:
        if r not in _REGISTRARS:
            _REGISTRARS.append(r)


def clear_tool_registrars() -> None:
    """Remove all registered tool registrars. Used by tests."""
    _REGISTRARS.clear()


# ----------------------------------------------------------------------
# Agent factory
# ----------------------------------------------------------------------


def _build_model_from_settings(settings: Settings) -> Model:
    """Construct a Pydantic-AI Model from settings.

    The agent layer is provider-agnostic — calling code may also pass a
    pre-built Model (e.g., TestModel or FunctionModel) to ``build_agent``
    to bypass this path entirely during tests.
    """
    if settings.test_mode:
        # Lazy import to avoid pulling test plumbing in production paths.
        from pydantic_ai.models.test import TestModel

        return TestModel()

    if settings.llm_provider == "openrouter":
        if not settings.openrouter_api_key:
            raise AgentError(
                "OPENROUTER_API_KEY is not set. Configure it in env/.env or "
                "set AVIATION_COPILOT_TEST_MODE=1 for offline development."
            )
        provider = OpenAIProvider(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )
        return OpenAIChatModel(settings.agent_model, provider=provider)

    raise AgentError(f"Unsupported llm_provider: {settings.llm_provider!r}")


def build_agent(
    *,
    model: Model | None = None,
    settings: Settings | None = None,
    apply_tool_registrars: bool = True,
) -> Agent[AgentDeps, str]:
    """Construct the configured agent.

    Args:
        model: Pre-built model (TestModel / FunctionModel / OpenAIModel). When
            None, the model is built from settings.
        settings: Override the cached settings (mostly for tests).
        apply_tool_registrars: When True (default), every registrar in the
            global registry runs against the new agent. Tests building an
            isolated agent typically pass False and register their own.

    Returns:
        A configured Pydantic-AI ``Agent`` ready for ``await agent.run(...)``.
    """
    settings = settings or get_settings()
    model = model or _build_model_from_settings(settings)

    agent: Agent[AgentDeps, str] = Agent(
        model,
        deps_type=AgentDeps,
        output_type=str,
        system_prompt=AVIATION_OPS_SYSTEM_PROMPT,
        retries=settings.agent_tool_retries,
    )
    if apply_tool_registrars:
        for register in _REGISTRARS:
            register(agent)
    return agent


# ----------------------------------------------------------------------
# Run with trace
# ----------------------------------------------------------------------


async def run_with_trace(
    question: str,
    *,
    agent: Agent[AgentDeps, str] | None = None,
    deps: AgentDeps | None = None,
    today_iso: str | None = None,
    settings: Settings | None = None,
) -> AgentResult:
    """Execute the agent on ``question`` and return answer + structured trace.

    The trace is mutated in-place by both this function (LLM-call summary on
    completion) and by tools (during their execution). On internal failure,
    returns a graceful AgentResult with a sanitized message and an error kind
    rather than raising.
    """
    settings = settings or get_settings()
    if agent is None:
        agent = build_agent(settings=settings)
    if deps is None:
        deps = AgentDeps(trace=Trace.new(question=question))

    prompt = render_question_with_context(question, today_iso=today_iso)
    started = time.perf_counter()
    try:
        run_result = await agent.run(prompt, deps=deps)
    except ToolError as exc:
        deps.trace.append_error(
            error_kind=f"tool_error:{exc.kind}",
            message=exc.user_message,
            retryable=exc.retryable,
        )
        deps.trace.finalize()
        return AgentResult(
            answer=_fallback_answer(exc),
            trace=deps.trace,
            error=f"tool_error:{exc.kind}",
        )
    except MaxStepsExceededError as exc:
        deps.trace.append_error(
            error_kind="max_steps_exceeded",
            message=exc.message,
            retryable=False,
        )
        deps.trace.finalize()
        return AgentResult(
            answer=(
                "I wasn't able to gather all the information needed before reaching "
                "my step limit. Try a more focused question, or check the trace for what was found."
            ),
            trace=deps.trace,
            error="max_steps_exceeded",
        )
    except AgentError as exc:
        deps.trace.append_error(error_kind="agent_error", message=str(exc))
        deps.trace.finalize()
        return AgentResult(
            answer="I hit an internal error before I could answer.",
            trace=deps.trace,
            error="agent_error",
        )

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    usage = _extract_usage(run_result)
    deps.trace.append_llm(
        model=settings.agent_model,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        latency_ms=elapsed_ms,
    )
    deps.trace.finalize()
    return AgentResult(answer=str(run_result.output), trace=deps.trace, error=None)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _fallback_answer(exc: ToolError) -> str:
    """Build a user-safe answer when the agent run terminated on a tool error."""
    return (
        "I couldn't complete that request because a required data source was "
        f"unavailable ({exc.user_message}). The trace shows which step failed."
    )


def _extract_usage(run_result: Any) -> dict[str, int | None]:
    """Extract token counts from a Pydantic-AI run result.

    Pydantic-AI 1.x exposes ``run_result.usage`` as a property returning a
    ``Usage`` object with ``input_tokens`` and ``output_tokens`` attributes.
    """
    out: dict[str, int | None] = {"input_tokens": None, "output_tokens": None}
    usage: Any = getattr(run_result, "usage", None)
    if usage is None:
        return out
    for field_name in ("input_tokens", "output_tokens"):
        val = getattr(usage, field_name, None)
        if val is not None:
            out[field_name] = int(val)
    return out


# Forward-declare async helpers callers can await for trace-aware tool wrappers.
# Used by tools (U5) to wrap their bodies in trace appendage; not used at U4.
__all__ = [
    "AgentDeps",
    "AgentResult",
    "ToolRegistrar",
    "build_agent",
    "clear_tool_registrars",
    "register_tools",
    "run_with_trace",
]


# Make the unused import surface noisy if mypy strips it.
_AwaitableType = Callable[..., Awaitable[Any]]
