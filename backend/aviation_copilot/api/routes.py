"""HTTP route handlers for the agent service."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse

from aviation_copilot import __version__
from aviation_copilot.agent.core import AgentDeps, run_with_trace
from aviation_copilot.agent.trace import Trace
from aviation_copilot.api.models import (
    HealthResponse,
    QueryRequest,
    QueryResponse,
    SseEvent,
    VersionResponse,
)

router = APIRouter()


# ----------------------------------------------------------------------
# /healthz
# ----------------------------------------------------------------------


@router.get("/healthz", response_model=HealthResponse)
async def healthz(request: Request) -> HealthResponse:
    """Liveness + readiness check. Returns 200 with the per-dep status."""
    state = request.app.state
    flight_ok = _flight_db_ready(state)
    corpus_ok = _corpus_ready(state)
    if flight_ok and corpus_ok:
        return HealthResponse(status="ok", flight_db_ready=True, corpus_index_ready=True)
    notes: list[str] = []
    if not flight_ok:
        notes.append("flight_db not loaded")
    if not corpus_ok:
        notes.append("corpus_index not loaded")
    return HealthResponse(
        status="degraded",
        flight_db_ready=flight_ok,
        corpus_index_ready=corpus_ok,
        notes=notes,
    )


def _flight_db_ready(state: object) -> bool:
    db = getattr(state, "flight_db", None)
    if db is None:
        return False
    try:
        return bool(db.row_count() > 0)
    except Exception:
        return False


def _corpus_ready(state: object) -> bool:
    idx = getattr(state, "corpus_index", None)
    if idx is None:
        return False
    try:
        return bool(idx.row_count() > 0)
    except Exception:
        return False


# ----------------------------------------------------------------------
# /version
# ----------------------------------------------------------------------


@router.get("/version", response_model=VersionResponse)
async def version(request: Request) -> VersionResponse:
    settings = request.app.state.settings
    return VersionResponse(
        version=__version__,
        git_sha=os.environ.get("GIT_SHA"),
        agent_model=settings.agent_model,
        judge_model=settings.judge_model,
        flight_data_version=getattr(request.app.state, "flight_data_version", None),
        corpus_version=getattr(request.app.state, "corpus_version", None),
    )


# ----------------------------------------------------------------------
# /trace/{trace_id}
# ----------------------------------------------------------------------


@router.get("/trace/{trace_id}", response_model=QueryResponse)
async def get_trace(request: Request, trace_id: str) -> QueryResponse:
    store: dict[str, QueryResponse] = request.app.state.trace_store
    item = store.get(trace_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trace not found")
    return item


# ----------------------------------------------------------------------
# /query — SSE streaming
# ----------------------------------------------------------------------


@router.post("/query")
async def query(request: Request, body: QueryRequest) -> Response:
    """Streaming agent invocation. Emits SSE events:

    - ``step``  : one per trace step as the agent runs (post-completion emit)
    - ``final`` : the QueryResponse payload
    - ``done``  : terminator
    """
    state = request.app.state
    ip = request.client.host if request.client else "unknown"

    # Per-IP rate limit
    allowed, retry_after = state.rate_limiter.check(ip)
    if not allowed:
        headers = {"Retry-After": str(int(retry_after) + 1)}
        return JSONResponse(
            content={"detail": "rate limit exceeded", "retry_after": retry_after},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers=headers,
        )

    # Daily token budget
    if not state.daily_budget.allow():
        return JSONResponse(
            content={
                "detail": "daily token budget exceeded — resets at UTC midnight",
                "used_today": state.daily_budget.used_today,
                "cap": state.daily_budget.cap,
            },
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    deps = AgentDeps(
        trace=Trace.new(question=body.question),
        flight_db=getattr(state, "flight_db", None),
        corpus_index=getattr(state, "corpus_index", None),
    )

    async def event_stream() -> AsyncIterator[bytes]:
        # Run the agent (non-streaming for v1; richer mid-flight streaming
        # via Pydantic-AI's agent.iter() can land as a follow-up without
        # changing the SSE envelope contract).
        result = await run_with_trace(
            body.question,
            agent=state.agent,
            deps=deps,
            today_iso=body.today_iso,
            settings=state.settings,
        )
        # Emit one `step` event per trace step.
        for step in result.trace.steps:
            yield _sse(SseEvent(type="step", payload=step))
            await asyncio.sleep(0)  # yield control between events for backpressure
        # Persist the final response so /trace/{id} can fetch it.
        final = QueryResponse(
            trace_id=result.trace.trace_id,
            answer=result.answer,
            trace=result.trace,
            error=result.error,
        )
        state.trace_store[result.trace.trace_id] = final
        state.daily_budget.add(
            result.trace.total_input_tokens() + result.trace.total_output_tokens()
        )
        yield _sse(SseEvent(type="final", payload=json.loads(final.model_dump_json())))
        yield _sse(SseEvent(type="done", payload={}))

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _sse(event: SseEvent) -> bytes:
    payload = event.model_dump_json()
    return f"data: {payload}\n\n".encode()
