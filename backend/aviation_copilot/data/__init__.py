"""Flight data layer — DuckDB-backed access to BTS On-Time Performance.

- :mod:`schema`        : Pydantic models for query inputs and outputs.
- :mod:`duckdb_client` : Typed query helpers consumed by the flight_data tool.
- :mod:`airports`      : Top-50 US airport ICAO/IATA constants.
"""

from aviation_copilot.data.airports import TOP_50_AIRPORTS, is_top_50
from aviation_copilot.data.duckdb_client import DuckDBClient
from aviation_copilot.data.schema import (
    DelayCauseSummary,
    FlightDataError,
    FlightSummary,
    RouteQuery,
    RouteSummary,
)

__all__ = [
    "TOP_50_AIRPORTS",
    "DelayCauseSummary",
    "DuckDBClient",
    "FlightDataError",
    "FlightSummary",
    "RouteQuery",
    "RouteSummary",
    "is_top_50",
]
