"""Pydantic models for flight data queries.

These models bound what the ``flight_data_query`` tool (U5) accepts from the
LLM and what it returns. The DuckDB layer never returns raw rows to the
agent — only structured summaries.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class FlightDataError(Exception):
    """Raised by the DuckDB client on structured query failures.

    Wraps DuckDB's native exceptions with a sanitized message (no SQL leaked
    to callers; the original error is preserved on ``__cause__``).
    """


class RouteQuery(BaseModel):
    """Input model for a route-level query.

    Either ``origin`` and ``dest`` may be omitted for system-wide queries, but
    at least one date must be supplied to bound the result set.
    """

    origin: str | None = Field(
        default=None,
        description="IATA or ICAO airport code for the origin (e.g. 'ORD' or 'KORD').",
        max_length=4,
    )
    dest: str | None = Field(
        default=None,
        description="IATA or ICAO airport code for the destination.",
        max_length=4,
    )
    start_date: date = Field(description="Inclusive start of the date window.")
    end_date: date = Field(description="Inclusive end of the date window.")
    airline: str | None = Field(
        default=None,
        description="Optional IATA airline code (e.g. 'AA', 'UA', 'WN').",
        max_length=2,
    )

    @field_validator("origin", "dest")
    @classmethod
    def _uppercase(cls, v: str | None) -> str | None:
        return v.upper() if v else v

    @field_validator("airline")
    @classmethod
    def _uppercase_airline(cls, v: str | None) -> str | None:
        return v.upper() if v else v

    def is_date_window_valid(self) -> bool:
        """Return True iff start_date <= end_date."""
        return self.start_date <= self.end_date


class FlightSummary(BaseModel):
    """Aggregate summary across the queried window.

    All counts and means are derived from rows that match the query filters.
    """

    total_flights: int = Field(ge=0)
    cancelled: int = Field(ge=0)
    diverted: int = Field(ge=0)
    on_time_arrivals: int = Field(ge=0, description="Arrivals within 15 minutes of schedule.")
    on_time_rate: float = Field(ge=0.0, le=1.0)
    mean_departure_delay_min: float | None = Field(
        default=None,
        description="Mean departure delay across non-cancelled flights, in minutes.",
    )
    mean_arrival_delay_min: float | None = Field(
        default=None,
        description="Mean arrival delay across non-cancelled flights, in minutes.",
    )
    median_arrival_delay_min: float | None = None


class DelayCauseSummary(BaseModel):
    """Mean minutes per delay-cause category for flights with reported delays."""

    carrier_min: float = Field(ge=0.0)
    weather_min: float = Field(ge=0.0)
    nas_min: float = Field(ge=0.0, description="National Air System (ATC, weather routing) delay.")
    security_min: float = Field(ge=0.0)
    late_aircraft_min: float = Field(ge=0.0)


class RouteSummary(BaseModel):
    """Per-route summary returned by route-level queries.

    A "route" is an (origin, dest) pair. When the query did not pin origin
    and dest, the response contains the top-K routes by flight volume.
    """

    origin: str
    dest: str
    origin_name: str | None = None
    dest_name: str | None = None
    flights: FlightSummary
    by_cause: DelayCauseSummary | None = None
    notable_observations: list[str] = Field(default_factory=list)


class AirlineFilter(BaseModel):
    """Optional airline filter shape, kept separate for tool I/O composition."""

    code: str = Field(description="IATA airline code, e.g. 'AA', 'UA', 'WN'.", max_length=2)
    role: Literal["operator", "marketing"] = "operator"
