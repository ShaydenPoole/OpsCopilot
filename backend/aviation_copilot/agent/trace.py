"""Structured tool-call / LLM-call trace for the agent loop.

A :class:`Trace` is an ordered append-only list of :class:`TraceStep` entries
that capture every interaction the agent had — LLM calls, tool calls, tool
results, errors. The trace is the contract between the agent (U4) and three
downstream consumers:

1. The FastAPI ``/trace/{id}`` endpoint (U6) — UI tool-trace inspector
2. The eval suite scorers (U7) — tool-call correctness, refusal detection
3. Langfuse spans (U8) — production observability

The trace is fully JSON-serializable via Pydantic for transport and storage.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

StepKind = Literal["llm_call", "tool_call", "tool_result", "error"]


# ----------------------------------------------------------------------
# Step variants
# ----------------------------------------------------------------------


class _BaseStep(BaseModel):
    """Shared metadata across all trace steps."""

    step_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    kind: StepKind
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LLMCallStep(_BaseStep):
    kind: Literal["llm_call"] = "llm_call"
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: float | None = None


class ToolCallStep(_BaseStep):
    kind: Literal["tool_call"] = "tool_call"
    tool_name: str
    args: dict[str, Any]
    attempt: int = 1


class ToolResultStep(_BaseStep):
    kind: Literal["tool_result"] = "tool_result"
    tool_name: str
    result_preview: str
    """Short truncated string for UI display. Full result lives in tool output."""
    success: bool = True
    latency_ms: float | None = None


class ErrorStep(_BaseStep):
    kind: Literal["error"] = "error"
    error_kind: str
    """e.g. 'tool_error:upstream_timeout' or 'max_steps_exceeded'."""
    message: str
    retryable: bool = False
    tool_name: str | None = None


TraceStep = Annotated[
    LLMCallStep | ToolCallStep | ToolResultStep | ErrorStep,
    Field(discriminator="kind"),
]


# ----------------------------------------------------------------------
# Trace container
# ----------------------------------------------------------------------


class Trace(BaseModel):
    """Append-only ordered list of agent steps for one ``/query`` invocation.

    Mutation happens only through :meth:`append`. JSON-serializable via
    standard ``model_dump_json``.
    """

    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    question: str = ""
    steps: list[TraceStep] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    @classmethod
    def new(cls, question: str = "") -> Trace:
        return cls(question=question, steps=[])

    def append(self, step: TraceStep) -> None:
        self.steps.append(step)

    def append_llm(
        self,
        *,
        model: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_usd: float | None = None,
        latency_ms: float | None = None,
    ) -> LLMCallStep:
        step = LLMCallStep(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )
        self.append(step)
        return step

    def append_tool_call(
        self, *, tool_name: str, args: dict[str, Any], attempt: int = 1
    ) -> ToolCallStep:
        step = ToolCallStep(tool_name=tool_name, args=args, attempt=attempt)
        self.append(step)
        return step

    def append_tool_result(
        self,
        *,
        tool_name: str,
        result_preview: str,
        success: bool = True,
        latency_ms: float | None = None,
    ) -> ToolResultStep:
        step = ToolResultStep(
            tool_name=tool_name,
            result_preview=result_preview,
            success=success,
            latency_ms=latency_ms,
        )
        self.append(step)
        return step

    def append_error(
        self,
        *,
        error_kind: str,
        message: str,
        retryable: bool = False,
        tool_name: str | None = None,
    ) -> ErrorStep:
        step = ErrorStep(
            error_kind=error_kind,
            message=message,
            retryable=retryable,
            tool_name=tool_name,
        )
        self.append(step)
        return step

    def finalize(self) -> None:
        if self.completed_at is None:
            self.completed_at = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Convenience accessors used by eval scorers (U7)
    # ------------------------------------------------------------------

    def tools_called(self) -> list[str]:
        """Unique tool names called in this trace, in first-call order."""
        seen: list[str] = []
        for step in self.steps:
            if isinstance(step, ToolCallStep) and step.tool_name not in seen:
                seen.append(step.tool_name)
        return seen

    def tool_call_count(self, tool_name: str | None = None) -> int:
        return sum(
            1
            for step in self.steps
            if isinstance(step, ToolCallStep) and (tool_name is None or step.tool_name == tool_name)
        )

    def errors(self) -> list[ErrorStep]:
        return [step for step in self.steps if isinstance(step, ErrorStep)]

    def total_cost_usd(self) -> float:
        return sum(step.cost_usd or 0.0 for step in self.steps if isinstance(step, LLMCallStep))

    def total_input_tokens(self) -> int:
        return sum(step.input_tokens or 0 for step in self.steps if isinstance(step, LLMCallStep))

    def total_output_tokens(self) -> int:
        return sum(step.output_tokens or 0 for step in self.steps if isinstance(step, LLMCallStep))
