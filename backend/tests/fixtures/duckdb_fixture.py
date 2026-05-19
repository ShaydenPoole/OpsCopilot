"""Build a small synthetic DuckDB file for unit tests.

The real BTS dataset is multi-GB. Tests run against a hand-crafted fixture
with deterministic flights covering the scenarios in the plan's U2 test
matrix: cancelled, on-time, late, multiple airports, multiple airlines.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb


def build_test_duckdb(path: Path) -> Path:
    """Create a small synthetic flights DuckDB at ``path``.

    Schema mirrors the production DuckDB exactly so query helpers don't need
    fixture-specific code paths.
    """
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(path))
    try:
        con.execute(
            """
            CREATE TABLE flights (
                flight_date            DATE,
                origin_iata            VARCHAR,
                dest_iata              VARCHAR,
                airline_iata           VARCHAR,
                flight_number          INTEGER,
                scheduled_dep_time_int INTEGER,
                scheduled_arr_time_int INTEGER,
                departure_delay_min    DOUBLE,
                arrival_delay_min      DOUBLE,
                cancelled              BOOLEAN,
                diverted               BOOLEAN,
                carrier_delay_min      DOUBLE,
                weather_delay_min      DOUBLE,
                nas_delay_min          DOUBLE,
                security_delay_min     DOUBLE,
                late_aircraft_min      DOUBLE
            )
            """
        )

        rows: list[tuple] = []
        base = date(2024, 7, 1)
        # 30 days x ~5 flights/day across a few routes
        for d in range(30):
            day = base + timedelta(days=d)
            # ORD -> LGA: 3 flights, one with weather delay, one cancelled, one on-time
            rows.append(
                (
                    day,
                    "ORD",
                    "LGA",
                    "AA",
                    100 + d,
                    800,
                    1100,
                    15.0,
                    22.0,
                    False,
                    False,
                    0.0,
                    22.0,
                    0.0,
                    0.0,
                    0.0,
                )
            )
            rows.append(
                (
                    day,
                    "ORD",
                    "LGA",
                    "UA",
                    200 + d,
                    1200,
                    1500,
                    None,
                    None,
                    True,
                    False,
                    None,
                    None,
                    None,
                    None,
                    None,
                )
            )
            rows.append(
                (
                    day,
                    "ORD",
                    "LGA",
                    "AA",
                    300 + d,
                    1700,
                    2000,
                    0.0,
                    5.0,
                    False,
                    False,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                )
            )
            # ATL -> MCO: 1 flight, on-time, no delay cause minutes
            rows.append(
                (
                    day,
                    "ATL",
                    "MCO",
                    "DL",
                    400 + d,
                    900,
                    1100,
                    0.0,
                    -3.0,
                    False,
                    False,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                )
            )
            # SFO -> SEA: 1 flight, late-aircraft delay
            rows.append(
                (
                    day,
                    "SFO",
                    "SEA",
                    "AS",
                    500 + d,
                    1400,
                    1630,
                    30.0,
                    28.0,
                    False,
                    False,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    28.0,
                )
            )

        con.executemany(
            "INSERT INTO flights VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        con.execute(
            "CREATE INDEX idx_flights_route_date ON flights(origin_iata, dest_iata, flight_date)"
        )
        con.execute("CREATE INDEX idx_flights_date ON flights(flight_date)")
    finally:
        con.close()
    return path
