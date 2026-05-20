"""Langfuse observability for agent runs (U8).

Each completed agent invocation is replayed into Langfuse as one trace whose
child observations mirror the structured
:class:`~aviation_copilot.agent.trace.Trace` — one generation per LLM call,
one tool span per tool call (paired with its result), one error span per
failure. The structured ``Trace`` is the single source of truth (see
``agent/trace.py``); replaying it *after* the run keeps observability off the
agent's hot path and means a Langfuse outage can never break a query.

When Langfuse credentials are unset — local dev, CI without secrets, eval
runs, test mode — :func:`build_observer` returns a :class:`NoopObserver` and
the agent runs completely untouched.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from aviation_copilot.agent.trace import ErrorStep, LLMCallStep, ToolCallStep, ToolResultStep
from aviation_copilot.config import Settings, get_settings

if TYPE_CHECKING:
    from aviation_copilot.agent.core import AgentResult

logger = logging.getLogger("aviation_copilot.observability")

# Langfuse observation type slugs used by this module.
_ROOT_TYPE = "agent"
_LLM_TYPE = "generation"
_TOOL_TYPE = "tool"
_ERROR_TYPE = "span"


# ----------------------------------------------------------------------
# Observer interface
# ----------------------------------------------------------------------


class AgentObserver(ABC):
    """Records completed agent runs to an observability backend.

    Implementations must never raise out of :meth:`record_run` — observability
    is best-effort and must not surface as an agent failure.
    """

    enabled: bool = False
    """True when runs are actually exported. ``False`` for :class:`NoopObserver`
    so callers can cheaply skip the work."""

    @abstractmethod
    def record_run(self, result: AgentResult) -> str | None:
        """Export one completed run. Returns the Langfuse trace URL, or None."""

    def flush(self) -> None:  # noqa: B027 — intentional optional hook, default no-op
        """Force-flush pending exports. Called once at app shutdown.

        Optional: the default is a no-op so :class:`NoopObserver` and any
        future fire-and-forget backend need not override it.
        """


class NoopObserver(AgentObserver):
    """Observer used when Langfuse is not configured. Does nothing."""

    enabled = False

    def record_run(self, result: AgentResult) -> str | None:
        return None


class LangfuseObserver(AgentObserver):
    """Exports agent runs to Langfuse Cloud.

    The Langfuse client is injected rather than constructed here so tests can
    pass a lightweight fake — see ``tests/unit/test_langfuse_integration.py``.
    The client only needs ``start_observation``, ``get_trace_url`` and
    ``flush``; that contract matches the Langfuse v4 SDK.
    """

    enabled = True

    def __init__(self, client: Any) -> None:
        self._client = client

    # -- public API ----------------------------------------------------

    def record_run(self, result: AgentResult) -> str | None:
        trace = result.trace
        try:
            root = self._client.start_observation(
                name="agent.query",
                as_type=_ROOT_TYPE,
                input={"question": trace.question},
                metadata={
                    "trace_id": trace.trace_id,
                    "tools_called": trace.tools_called(),
                    "step_count": len(trace.steps),
                    "input_tokens": trace.total_input_tokens(),
                    "output_tokens": trace.total_output_tokens(),
                    "cost_usd": trace.total_cost_usd(),
                },
            )
            try:
                self._emit_steps(root, trace.steps)
                root.update(
                    output={"answer": result.answer},
                    level="ERROR" if result.error else "DEFAULT",
                    status_message=result.error,
                )
            finally:
                root.end()
            return self._trace_url(root)
        except Exception:
            logger.warning("Langfuse trace export failed", exc_info=True)
            return None

    def flush(self) -> None:
        try:
            self._client.flush()
        except Exception:
            logger.warning("Langfuse flush failed", exc_info=True)

    # -- step emission -------------------------------------------------

    def _emit_steps(self, root: Any, steps: list[Any]) -> None:
        """Walk the trace, emitting one child observation per logical step.

        A ``tool_call`` is paired with the immediately-following ``tool_result``
        or ``error`` for the same tool so the tool span carries both input and
        outcome. Top-level errors (``tool_name is None``) emit standalone.
        """
        i = 0
        n = len(steps)
        while i < n:
            step = steps[i]
            if isinstance(step, LLMCallStep):
                self._emit_llm(root, step)
                i += 1
            elif isinstance(step, ToolCallStep):
                outcome = steps[i + 1] if i + 1 < n else None
                if isinstance(outcome, ToolResultStep | ErrorStep) and (
                    getattr(outcome, "tool_name", None) == step.tool_name
                ):
                    self._emit_tool(root, step, outcome)
                    i += 2
                else:
                    self._emit_tool(root, step, None)
                    i += 1
            elif isinstance(step, ErrorStep):
                self._emit_error(root, step)
                i += 1
            else:  # orphan ToolResultStep — defensive, should not happen
                i += 1

    def _emit_llm(self, root: Any, step: LLMCallStep) -> None:
        kwargs: dict[str, Any] = {
            "name": "llm.call",
            "as_type": _LLM_TYPE,
            "model": step.model,
            "metadata": {"latency_ms": step.latency_ms, "step_id": step.step_id},
        }
        usage = _usage_details(step)
        if usage is not None:
            kwargs["usage_details"] = usage
        if step.cost_usd is not None:
            kwargs["cost_details"] = {"total": step.cost_usd}
        root.start_observation(**kwargs).end()

    def _emit_tool(
        self, root: Any, call: ToolCallStep, outcome: ToolResultStep | ErrorStep | None
    ) -> None:
        success = True
        level = "DEFAULT"
        status: str | None = None
        output: Any = None
        latency: float | None = None

        if isinstance(outcome, ToolResultStep):
            success = outcome.success
            output = outcome.result_preview
            latency = outcome.latency_ms
            if not success:
                level, status = "ERROR", "tool reported failure"
        elif isinstance(outcome, ErrorStep):
            success = False
            level, status = "ERROR", outcome.message
            output = {"error_kind": outcome.error_kind, "message": outcome.message}

        root.start_observation(
            name=f"tool.{call.tool_name}",
            as_type=_TOOL_TYPE,
            input=call.args,
            output=output,
            level=level,
            status_message=status,
            metadata={"attempt": call.attempt, "latency_ms": latency, "success": success},
        ).end()

    def _emit_error(self, root: Any, step: ErrorStep) -> None:
        root.start_observation(
            name=f"error.{step.error_kind}",
            as_type=_ERROR_TYPE,
            level="ERROR",
            status_message=step.message,
            metadata={
                "error_kind": step.error_kind,
                "retryable": step.retryable,
                "tool_name": step.tool_name,
            },
        ).end()

    def _trace_url(self, root: Any) -> str | None:
        try:
            otel_trace_id = getattr(root, "trace_id", None)
            if not otel_trace_id:
                return None
            url = self._client.get_trace_url(trace_id=otel_trace_id)
            return url if isinstance(url, str) else None
        except Exception:
            return None


def _usage_details(step: LLMCallStep) -> dict[str, int] | None:
    """Map an LLM step's token counts to Langfuse's ``usage_details`` shape."""
    if step.input_tokens is None and step.output_tokens is None:
        return None
    return {
        "input": step.input_tokens or 0,
        "output": step.output_tokens or 0,
    }


# ----------------------------------------------------------------------
# Factory
# ----------------------------------------------------------------------


def build_observer(settings: Settings | None = None) -> AgentObserver:
    """Construct the observer appropriate to the current configuration.

    Returns a :class:`NoopObserver` in test mode or whenever Langfuse
    credentials are absent — so local dev and CI never need real keys.
    """
    settings = settings or get_settings()
    if settings.test_mode or not settings.is_langfuse_configured:
        return NoopObserver()
    try:
        from langfuse import Langfuse

        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        return LangfuseObserver(client)
    except Exception:
        logger.warning("Langfuse client init failed; observability disabled", exc_info=True)
        return NoopObserver()


@lru_cache(maxsize=1)
def get_observer() -> AgentObserver:
    """Return a process-wide cached observer.

    Tests that change Langfuse env vars must call ``get_observer.cache_clear()``
    (mirrors the ``get_settings`` pattern in :mod:`aviation_copilot.config`).
    """
    return build_observer()
