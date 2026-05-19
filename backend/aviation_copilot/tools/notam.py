"""``notam_lookup`` tool — current NOTAMs for a specific airport.

Primary source: ``https://aviationweather.gov/api/data/notam`` (public, no
key required, reasonable rate limits for portfolio traffic). The FAA's
NOTAM Search API is the authoritative source but requires registration;
left as a fallback configurable via ``FAA_NOTAM_API_KEY``.
"""

from __future__ import annotations

import time

import httpx
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from aviation_copilot.agent.core import AgentDeps
from aviation_copilot.agent.errors import ToolError
from aviation_copilot.tools._base import map_http_error, new_http_client, truncate_for_trace

TOOL_NAME = "notam_lookup"
AWC_NOTAM_BASE = "https://aviationweather.gov"


class NotamEntry(BaseModel):
    """One NOTAM record as the agent should see it."""

    notam_id: str
    icao: str
    text: str
    """Full NOTAM text — agent should quote relevant portions."""
    issued_at: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    classification: str | None = None
    """e.g. 'INTL', 'DOM', or NOTAM type code."""


class NotamLookupResult(BaseModel):
    icao: str
    notams: list[NotamEntry] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    source_url: str = AWC_NOTAM_BASE


def register(agent: Agent[AgentDeps, str]) -> None:
    @agent.tool
    async def notam_lookup(
        ctx: RunContext[AgentDeps],
        icao: str = Field(description="ICAO airport code, 4 letters (e.g. 'KORD')."),
    ) -> NotamLookupResult:
        """Look up current NOTAMs (Notices to Air Missions) for an airport.

        Use for: runway closures, equipment outages, temporary restrictions,
        navaid status. Returns a list of active NOTAMs with their text and
        validity windows. Returns an empty list (not an error) when no
        NOTAMs are currently active.
        """
        return await _execute(ctx.deps, icao=icao)


async def _execute(deps: AgentDeps, *, icao: str) -> NotamLookupResult:
    started = time.perf_counter()
    deps.trace.append_tool_call(tool_name=TOOL_NAME, args={"icao": icao})

    icao_upper = icao.upper()
    if len(icao_upper) != 4 or not icao_upper.isalpha():
        msg = f"icao must be a 4-letter ICAO code; got {icao!r}"
        deps.trace.append_error(
            error_kind="tool_error:invalid_input", message=msg, tool_name=TOOL_NAME
        )
        raise ToolError(kind="invalid_input", retryable=False, user_message=msg)

    client = deps.extras.get("http_client") or new_http_client(base_url=AWC_NOTAM_BASE)
    owns_client = "http_client" not in deps.extras
    result = NotamLookupResult(icao=icao_upper)
    try:
        resp = await client.get(
            "/api/data/notam",
            params={"ids": icao_upper, "format": "json"},
        )
        resp.raise_for_status()
        payload = resp.json()
    except httpx.HTTPError as exc:
        deps.trace.append_error(
            error_kind="tool_error:unavailable",
            message=str(exc),
            tool_name=TOOL_NAME,
        )
        if owns_client:
            await client.aclose()
        raise map_http_error(exc, source="NOTAM service") from exc
    finally:
        if owns_client:
            await client.aclose()

    items = payload if isinstance(payload, list) else payload.get("data", [])
    for raw in items:
        entry = _parse_notam(raw, icao_upper)
        if entry is not None:
            result.notams.append(entry)

    if not result.notams:
        result.notes.append(f"No active NOTAMs returned for {icao_upper}.")

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    deps.trace.append_tool_result(
        tool_name=TOOL_NAME,
        result_preview=truncate_for_trace(
            f"{len(result.notams)} NOTAMs for {icao_upper}"
            + (f": {result.notams[0].text[:120]}" if result.notams else "")
        ),
        success=True,
        latency_ms=elapsed_ms,
    )
    return result


def _parse_notam(raw: dict[str, object] | object, icao: str) -> NotamEntry | None:
    """Normalize one upstream record into a NotamEntry. Returns None when the
    record is too sparse to be useful.
    """
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("notamText") or raw.get("text") or raw.get("rawText") or "").strip()
    if not text:
        return None
    return NotamEntry(
        notam_id=str(raw.get("notamId") or raw.get("id") or "")[:64],
        icao=icao,
        text=text,
        issued_at=_as_iso(raw.get("issuedDate") or raw.get("issueDate")),
        effective_from=_as_iso(raw.get("effectiveStart") or raw.get("startValidity")),
        effective_to=_as_iso(raw.get("effectiveEnd") or raw.get("endValidity")),
        classification=str(raw.get("classification") or raw.get("type") or "") or None,
    )


def _as_iso(v: object) -> str | None:
    if v is None or v == "":
        return None
    return str(v)
