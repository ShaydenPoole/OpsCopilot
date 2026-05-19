"""Request, SSE-envelope, and response models for the API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from aviation_copilot.agent.trace import Trace, TraceStep


class QueryRequest(BaseModel):
    """``POST /query`` request body."""

    question: str = Field(min_length=1, max_length=2000)
    today_iso: str | None = Field(
        default=None,
        description="Optional override for 'today' in agent prompts. Tests pin this.",
    )


# ----------------------------------------------------------------------
# SSE event envelope
# ----------------------------------------------------------------------


SseEventType = Literal["step", "delta", "final", "error", "done"]


class SseEvent(BaseModel):
    """One SSE event emitted from ``/query``.

    Client consumers parse ``data:`` lines as JSON and read ``type`` to
    dispatch. ``payload`` shape depends on ``type``:

    - ``step``    : :class:`TraceStep` (one trace entry)
    - ``delta``   : ``{"text": "..."}`` partial answer token
    - ``final``   : :class:`QueryResponse` (answer + trace + error)
    - ``error``   : ``{"kind": "...", "message": "..."}``
    - ``done``    : ``{}`` — signals stream end, harmless terminator
    """

    type: SseEventType
    payload: dict[str, Any] | TraceStep | None = None


class QueryResponse(BaseModel):
    """Final response payload for ``/query``.

    The same shape is returned both at the end of the SSE stream as a
    ``final`` event payload and from the (non-streaming) ``/query/sync``
    endpoint when callers don't want SSE.
    """

    trace_id: str
    answer: str
    trace: Trace
    error: str | None = None


# ----------------------------------------------------------------------
# Other endpoints
# ----------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    flight_db_ready: bool
    corpus_index_ready: bool
    notes: list[str] = Field(default_factory=list)


class VersionResponse(BaseModel):
    name: str = "aviation-ops-copilot"
    version: str
    git_sha: str | None = None
    agent_model: str
    judge_model: str
    flight_data_version: dict[str, Any] | None = None
    corpus_version: dict[str, Any] | None = None
