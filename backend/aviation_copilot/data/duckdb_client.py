"""Typed DuckDB query helpers for the flight data layer.

Schema (one fact table, two small dimensions):

    flights
        flight_date          DATE
        origin_iata          VARCHAR(3)
        origin_icao          VARCHAR(4)
        dest_iata            VARCHAR(3)
        dest_icao            VARCHAR(4)
        airline_iata         VARCHAR(2)
        flight_number        INTEGER
        scheduled_dep_time   TIME
        scheduled_arr_time   TIME
        departure_delay_min  DOUBLE        -- nullable; null when cancelled
        arrival_delay_min    DOUBLE        -- nullable
        cancelled            BOOLEAN
        diverted             BOOLEAN
        carrier_delay_min    DOUBLE        -- delay-cause breakdown; nullable
        weather_delay_min    DOUBLE
        nas_delay_min        DOUBLE
        security_delay_min   DOUBLE
        late_aircraft_min    DOUBLE

    airlines  (airline_iata -> name)
    airports  (iata -> icao, name)
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import duckdb

from aviation_copilot.data.airports import airport_name, iata_to_icao, icao_to_iata
from aviation_copilot.data.schema import (
    DelayCauseSummary,
    FlightDataError,
    FlightSummary,
    RouteQuery,
    RouteSummary,
)

if TYPE_CHECKING:
    pass


class DuckDBClient:
    """Read-only DuckDB client for the flights database.

    Open as a context manager or construct once at app startup and pass the
    instance into tools. The underlying connection is thread-safe for reads
    when accessed via separate cursors.
    """

    def __init__(self, db_path: str | Path, *, read_only: bool = True) -> None:
        self._db_path = Path(db_path)
        self._read_only = read_only
        self._conn: duckdb.DuckDBPyConnection | None = None

    def connect(self) -> None:
        if self._conn is not None:
            return
        if self._read_only and not self._db_path.exists():
            raise FlightDataError(
                f"DuckDB file not found at {self._db_path}. "
                "Run data_pipeline/build_flight_duckdb.py to create it."
            )
        try:
            self._conn = duckdb.connect(str(self._db_path), read_only=self._read_only)
        except duckdb.Error as exc:
            raise FlightDataError(f"Failed to open DuckDB at {self._db_path}.") from exc

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> DuckDBClient:
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @property
    def _c(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            raise FlightDataError("DuckDBClient is not connected. Call .connect() first.")
        return self._conn

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------

    def summarize_route(self, query: RouteQuery) -> RouteSummary:
        """Aggregate one origin-destination pair over the date window.

        Both ``origin`` and ``dest`` must be supplied. For top-routes
        across an origin/destination, use :meth:`top_routes` instead.

        Raises:
            FlightDataError: if the query window is invalid, the airports
                are unknown, or DuckDB itself errors.
        """
        if not query.origin or not query.dest:
            raise FlightDataError("summarize_route requires both origin and dest.")
        if not query.is_date_window_valid():
            raise FlightDataError(f"Invalid date window: {query.start_date} > {query.end_date}.")

        origin_iata, _origin_icao = _resolve_codes(query.origin)
        dest_iata, _dest_icao = _resolve_codes(query.dest)

        sql, params = _build_summary_sql(
            origin_iata=origin_iata,
            dest_iata=dest_iata,
            start_date=query.start_date.isoformat(),
            end_date=query.end_date.isoformat(),
            airline=query.airline,
        )
        try:
            row = self._c.execute(sql, params).fetchone()
        except duckdb.Error as exc:
            raise FlightDataError("Failed to execute route summary query.") from exc

        flights = _row_to_flight_summary(row)
        # `flights.total_flights > 0` guarantees `row` is not None (zero-row results
        # produce `total_flights == 0` via _row_to_flight_summary's None branch).
        by_cause = (
            _row_to_delay_cause_summary(row)
            if (flights.total_flights > 0 and row is not None)
            else None
        )

        return RouteSummary(
            origin=origin_iata,
            dest=dest_iata,
            origin_name=airport_name(origin_iata),
            dest_name=airport_name(dest_iata),
            flights=flights,
            by_cause=by_cause,
            notable_observations=_derive_notable_observations(flights, by_cause),
        )

    def top_routes_from(
        self,
        origin: str,
        start_date: str,
        end_date: str,
        *,
        limit: int = 10,
    ) -> list[RouteSummary]:
        """Return the top ``limit`` destinations by flight volume out of ``origin``."""
        origin_iata, _ = _resolve_codes(origin)
        sql = """
            SELECT
                dest_iata,
                COUNT(*) AS total,
                SUM(CASE WHEN cancelled THEN 1 ELSE 0 END) AS cancelled,
                SUM(CASE WHEN diverted THEN 1 ELSE 0 END) AS diverted,
                SUM(CASE WHEN COALESCE(arrival_delay_min, 1e9) <= 15 AND NOT cancelled THEN 1 ELSE 0 END) AS on_time,
                AVG(departure_delay_min) FILTER (WHERE NOT cancelled) AS mean_dep,
                AVG(arrival_delay_min) FILTER (WHERE NOT cancelled) AS mean_arr,
                MEDIAN(arrival_delay_min) FILTER (WHERE NOT cancelled) AS median_arr,
                AVG(COALESCE(carrier_delay_min, 0))      AS mean_carrier,
                AVG(COALESCE(weather_delay_min, 0))      AS mean_weather,
                AVG(COALESCE(nas_delay_min, 0))          AS mean_nas,
                AVG(COALESCE(security_delay_min, 0))     AS mean_security,
                AVG(COALESCE(late_aircraft_min, 0))      AS mean_late_ac
            FROM flights
            WHERE origin_iata = ?
              AND flight_date BETWEEN ? AND ?
            GROUP BY dest_iata
            ORDER BY total DESC
            LIMIT ?
        """
        try:
            rows = self._c.execute(sql, [origin_iata, start_date, end_date, limit]).fetchall()
        except duckdb.Error as exc:
            raise FlightDataError("Failed to execute top_routes_from query.") from exc

        result: list[RouteSummary] = []
        for row in rows:
            dest = row[0]
            flights = FlightSummary(
                total_flights=int(row[1]),
                cancelled=int(row[2]),
                diverted=int(row[3]),
                on_time_arrivals=int(row[4]),
                on_time_rate=(int(row[4]) / int(row[1])) if row[1] else 0.0,
                mean_departure_delay_min=float(row[5]) if row[5] is not None else None,
                mean_arrival_delay_min=float(row[6]) if row[6] is not None else None,
                median_arrival_delay_min=float(row[7]) if row[7] is not None else None,
            )
            by_cause = DelayCauseSummary(
                carrier_min=float(row[8] or 0.0),
                weather_min=float(row[9] or 0.0),
                nas_min=float(row[10] or 0.0),
                security_min=float(row[11] or 0.0),
                late_aircraft_min=float(row[12] or 0.0),
            )
            result.append(
                RouteSummary(
                    origin=origin_iata,
                    dest=dest,
                    origin_name=airport_name(origin_iata),
                    dest_name=airport_name(dest),
                    flights=flights,
                    by_cause=by_cause,
                    notable_observations=_derive_notable_observations(flights, by_cause),
                )
            )
        return result

    def row_count(self) -> int:
        """Return total row count in ``flights``. Used by ``/healthz``."""
        try:
            row = self._c.execute("SELECT COUNT(*) FROM flights").fetchone()
        except duckdb.Error as exc:
            raise FlightDataError("Failed to read row count.") from exc
        return int(row[0]) if row else 0

    @contextmanager
    def raw_cursor(self) -> Iterator[duckdb.DuckDBPyConnection]:
        """Yield the underlying DuckDB connection for ad-hoc analysis scripts.

        Not used by the agent at runtime — exposed for the data pipeline and
        for one-off notebook inspection during development.
        """
        yield self._c


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


def _resolve_codes(code: str) -> tuple[str, str | None]:
    """Return (IATA, ICAO) for a code that may be IATA or ICAO. Both fall back
    to the input string if not in the top-50 set — callers decide policy.
    """
    upper = code.upper()
    if len(upper) == 3:
        return upper, iata_to_icao(upper)
    if len(upper) == 4:
        iata = icao_to_iata(upper)
        return (iata or upper, upper)
    return upper, None


def _build_summary_sql(
    *,
    origin_iata: str,
    dest_iata: str,
    start_date: str,
    end_date: str,
    airline: str | None,
) -> tuple[str, list[Any]]:
    where = [
        "origin_iata = ?",
        "dest_iata = ?",
        "flight_date BETWEEN ? AND ?",
    ]
    params: list[Any] = [origin_iata, dest_iata, start_date, end_date]
    if airline:
        where.append("airline_iata = ?")
        params.append(airline)
    # The f-string composes a SQL WHERE clause from a list of hardcoded
    # predicate strings (`where`) — never from user input. All caller-supplied
    # values flow through `?` placeholders via the `params` list, which DuckDB
    # binds as parameters. Safe from injection; the ruff S608 finding here is
    # a false positive against this construction pattern.
    sql = f"""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN cancelled THEN 1 ELSE 0 END) AS cancelled,
            SUM(CASE WHEN diverted THEN 1 ELSE 0 END) AS diverted,
            SUM(CASE WHEN COALESCE(arrival_delay_min, 1e9) <= 15 AND NOT cancelled THEN 1 ELSE 0 END) AS on_time,
            AVG(departure_delay_min) FILTER (WHERE NOT cancelled) AS mean_dep,
            AVG(arrival_delay_min) FILTER (WHERE NOT cancelled) AS mean_arr,
            MEDIAN(arrival_delay_min) FILTER (WHERE NOT cancelled) AS median_arr,
            AVG(COALESCE(carrier_delay_min, 0))      AS mean_carrier,
            AVG(COALESCE(weather_delay_min, 0))      AS mean_weather,
            AVG(COALESCE(nas_delay_min, 0))          AS mean_nas,
            AVG(COALESCE(security_delay_min, 0))     AS mean_security,
            AVG(COALESCE(late_aircraft_min, 0))      AS mean_late_ac
        FROM flights
        WHERE {" AND ".join(where)}
    """  # noqa: S608
    return sql, params


def _row_to_flight_summary(row: tuple[Any, ...] | None) -> FlightSummary:
    if row is None or row[0] == 0:
        return FlightSummary(
            total_flights=0,
            cancelled=0,
            diverted=0,
            on_time_arrivals=0,
            on_time_rate=0.0,
            mean_departure_delay_min=None,
            mean_arrival_delay_min=None,
            median_arrival_delay_min=None,
        )
    total = int(row[0])
    on_time = int(row[3])
    return FlightSummary(
        total_flights=total,
        cancelled=int(row[1]),
        diverted=int(row[2]),
        on_time_arrivals=on_time,
        on_time_rate=(on_time / total) if total else 0.0,
        mean_departure_delay_min=float(row[4]) if row[4] is not None else None,
        mean_arrival_delay_min=float(row[5]) if row[5] is not None else None,
        median_arrival_delay_min=float(row[6]) if row[6] is not None else None,
    )


def _row_to_delay_cause_summary(row: tuple[Any, ...]) -> DelayCauseSummary:
    return DelayCauseSummary(
        carrier_min=float(row[7] or 0.0),
        weather_min=float(row[8] or 0.0),
        nas_min=float(row[9] or 0.0),
        security_min=float(row[10] or 0.0),
        late_aircraft_min=float(row[11] or 0.0),
    )


def _derive_notable_observations(
    flights: FlightSummary,
    by_cause: DelayCauseSummary | None,
) -> list[str]:
    """Surface a few human-readable observations the agent can quote verbatim."""
    notes: list[str] = []
    if flights.total_flights == 0:
        notes.append("No flights matched these filters in the loaded data window.")
        return notes
    if flights.on_time_rate < 0.65:
        notes.append(
            f"On-time arrival rate is {flights.on_time_rate:.0%} — well below the "
            "industry baseline (~80%)."
        )
    elif flights.on_time_rate > 0.85:
        notes.append(
            f"Strong on-time performance: {flights.on_time_rate:.0%} arrivals within 15 min."
        )
    if flights.cancelled / max(flights.total_flights, 1) > 0.05:
        notes.append(
            f"Elevated cancellation rate: {flights.cancelled / flights.total_flights:.1%}."
        )
    if by_cause:
        top = max(
            ("carrier", by_cause.carrier_min),
            ("weather", by_cause.weather_min),
            ("NAS / ATC", by_cause.nas_min),
            ("late aircraft", by_cause.late_aircraft_min),
            key=lambda kv: kv[1],
        )
        if top[1] > 0:
            notes.append(f"Dominant delay cause by mean minutes: {top[0]} ({top[1]:.1f} min).")
    return notes
