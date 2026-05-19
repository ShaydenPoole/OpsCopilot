"""``weather_lookup`` tool — current METAR/TAF from NOAA Aviation Weather.

Endpoint: ``https://aviationweather.gov/api/data/metar`` and ``.../taf``.
Returns raw text plus a parsed summary. No API key required.
"""

from __future__ import annotations

import time
from typing import Literal

import httpx
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from aviation_copilot.agent.core import AgentDeps
from aviation_copilot.agent.errors import ToolError
from aviation_copilot.tools._base import map_http_error, new_http_client, truncate_for_trace

TOOL_NAME = "weather_lookup"
AWC_BASE_URL = "https://aviationweather.gov"

WeatherProduct = Literal["metar", "taf", "both"]


class WeatherReport(BaseModel):
    """One METAR or TAF report."""

    product: Literal["METAR", "TAF"]
    icao: str
    raw_text: str
    issued_at: str | None = None
    """ISO timestamp of issue, when parseable from the JSON payload."""
    summary: str
    """Short human-readable summary of conditions; safe to quote to the user."""
    stale: bool = False
    """True when the METAR is older than ~2 hours; agent should reflect that."""


class WeatherLookupResult(BaseModel):
    icao: str
    reports: list[WeatherReport] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    """Free-form notes the agent can echo (e.g. 'no TAF issued for KMDW')."""
    source_url: str = AWC_BASE_URL


def register(agent: Agent[AgentDeps, str]) -> None:
    @agent.tool
    async def weather_lookup(
        ctx: RunContext[AgentDeps],
        icao: str = Field(description="ICAO airport code, 4 letters (e.g. 'KORD', 'KJFK')."),
        product: WeatherProduct = Field(
            default="metar",
            description="'metar', 'taf', or 'both'. Default 'metar'.",
        ),
    ) -> WeatherLookupResult:
        """Look up current METAR / TAF for an airport via NOAA Aviation Weather.

        Use this for live weather observations (METAR) and short-horizon
        forecasts (TAF). Returns raw report text plus a parsed summary
        the agent can quote with citation.
        """
        return await _execute(ctx.deps, icao=icao, product=product)


async def _execute(
    deps: AgentDeps,
    *,
    icao: str,
    product: WeatherProduct,
) -> WeatherLookupResult:
    started = time.perf_counter()
    deps.trace.append_tool_call(tool_name=TOOL_NAME, args={"icao": icao, "product": product})

    icao_upper = icao.upper()
    if len(icao_upper) != 4 or not icao_upper.isalpha():
        msg = f"icao must be a 4-letter ICAO code; got {icao!r}"
        deps.trace.append_error(
            error_kind="tool_error:invalid_input", message=msg, tool_name=TOOL_NAME
        )
        raise ToolError(kind="invalid_input", retryable=False, user_message=msg)

    products: list[Literal["METAR", "TAF"]] = (
        ["METAR"] if product == "metar" else ["TAF"] if product == "taf" else ["METAR", "TAF"]
    )

    result = WeatherLookupResult(icao=icao_upper)
    client = deps.extras.get("http_client") or new_http_client(base_url=AWC_BASE_URL)
    owns_client = "http_client" not in deps.extras
    try:
        for p in products:
            report = await _fetch_one(client, icao_upper, p)
            if report is None:
                result.notes.append(f"No {p} currently available for {icao_upper}.")
                continue
            result.reports.append(report)
    except httpx.HTTPError as exc:
        deps.trace.append_error(
            error_kind="tool_error:unavailable",
            message=str(exc),
            tool_name=TOOL_NAME,
        )
        if owns_client:
            await client.aclose()
        raise map_http_error(exc, source="NOAA Aviation Weather") from exc
    finally:
        if owns_client:
            await client.aclose()

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    preview_parts = [r.summary for r in result.reports] or result.notes or ["no data"]
    deps.trace.append_tool_result(
        tool_name=TOOL_NAME,
        result_preview=truncate_for_trace(" | ".join(preview_parts)),
        success=True,
        latency_ms=elapsed_ms,
    )
    return result


async def _fetch_one(
    client: httpx.AsyncClient,
    icao: str,
    product: Literal["METAR", "TAF"],
) -> WeatherReport | None:
    path = "/api/data/metar" if product == "METAR" else "/api/data/taf"
    resp = await client.get(
        path, params={"ids": icao, "format": "json", "taf": "true" if product == "TAF" else "false"}
    )
    resp.raise_for_status()
    payload = resp.json()
    if not payload:
        return None
    # AWC returns a list; take the first entry for the requested ICAO.
    record = payload[0] if isinstance(payload, list) else payload
    raw_text = str(record.get("rawOb") or record.get("rawTaf") or record.get("raw") or "").strip()
    issued = record.get("obsTime") or record.get("issueTime") or record.get("validTimeFrom")
    issued_iso = str(issued) if issued is not None else None
    return WeatherReport(
        product=product,
        icao=icao,
        raw_text=raw_text,
        issued_at=issued_iso,
        summary=_summarize(product, record, raw_text),
        stale=_is_stale(product, record),
    )


def _summarize(product: str, record: dict[str, object], raw_text: str) -> str:
    """Compact, agent-friendly summary; raw text is also available for quoting."""
    if product == "METAR":
        wind = record.get("wspd")
        vis = record.get("visib")
        temp = record.get("temp")
        flight_cat = record.get("fltCat")
        bits = []
        if flight_cat:
            bits.append(f"flight cat {flight_cat}")
        if wind is not None:
            bits.append(f"wind {wind}kt")
        if vis is not None:
            bits.append(f"vis {vis}sm")
        if temp is not None:
            bits.append(f"temp {temp}C")
        if bits:
            return ", ".join(bits)
    if not raw_text:
        return f"{product} for {record.get('icaoId', '?')} (no parsed summary available)"
    return raw_text[:160]


def _is_stale(product: str, record: dict[str, object]) -> bool:
    """METAR is considered stale after 2 hours. TAF staleness is more complex
    and we leave it false here — the agent can inspect ``issued_at`` directly.
    """
    if product != "METAR":
        return False
    obs_time = record.get("obsTime")
    if not isinstance(obs_time, (int, float)):
        return False
    # AWC encodes obsTime as a unix epoch in seconds.
    import time as _time

    age_hours = (_time.time() - float(obs_time)) / 3600.0
    return age_hours > 2.0
