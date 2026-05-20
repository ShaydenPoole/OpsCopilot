"""Tests for the DuckDB client.

Uses a small synthetic fixture (see tests/fixtures/duckdb_fixture.py) so tests
are deterministic, fast, and require no real data download.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from aviation_copilot.data.duckdb_client import DuckDBClient
from aviation_copilot.data.schema import FlightDataError, RouteQuery

from tests.fixtures.duckdb_fixture import build_test_duckdb


@pytest.fixture(scope="module")
def fixture_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("flightdata") / "flights.duckdb"
    return build_test_duckdb(path)


@pytest.fixture
def client(fixture_db: Path) -> DuckDBClient:
    c = DuckDBClient(fixture_db, read_only=True)
    c.connect()
    yield c
    c.close()


class TestConnectivity:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        c = DuckDBClient(tmp_path / "nonexistent.duckdb", read_only=True)
        with pytest.raises(FlightDataError, match="not found"):
            c.connect()

    def test_row_count_reports_fixture_size(self, client: DuckDBClient) -> None:
        # 30 days x 5 flights/day = 150 rows in the fixture.
        assert client.row_count() == 150


class TestSummarizeRoute:
    def test_happy_path_ord_lga(self, client: DuckDBClient) -> None:
        q = RouteQuery(
            origin="ORD",
            dest="LGA",
            start_date=date(2024, 7, 1),
            end_date=date(2024, 7, 31),
        )
        rs = client.summarize_route(q)
        assert rs.origin == "ORD"
        assert rs.dest == "LGA"
        # 3 flights/day x 30 days = 90 rows for ORD->LGA
        assert rs.flights.total_flights == 90
        # 30 cancelled (UA flights), 60 active
        assert rs.flights.cancelled == 30
        # On-time = arrival_delay <= 15, not cancelled.
        # AA 100 series: arrival_delay=22 (NOT on-time). AA 300 series: 5 (on-time). UA 200: cancelled.
        # So 30 on-time arrivals from AA 300 series.
        assert rs.flights.on_time_arrivals == 30
        assert rs.flights.on_time_rate == pytest.approx(30 / 90)
        # Mean dep delay across non-cancelled = (15 + 0) / 2 = 7.5
        assert rs.flights.mean_departure_delay_min == pytest.approx(7.5)

    def test_airline_filter(self, client: DuckDBClient) -> None:
        q = RouteQuery(
            origin="ORD",
            dest="LGA",
            airline="AA",
            start_date=date(2024, 7, 1),
            end_date=date(2024, 7, 31),
        )
        rs = client.summarize_route(q)
        # Only AA flights - 2/day x 30 = 60
        assert rs.flights.total_flights == 60
        # No AA cancellations in fixture
        assert rs.flights.cancelled == 0

    def test_unknown_airport_returns_zero(self, client: DuckDBClient) -> None:
        # "XYZ" is not in the fixture data at all.
        q = RouteQuery(
            origin="XYZ",
            dest="ABC",
            start_date=date(2024, 7, 1),
            end_date=date(2024, 7, 31),
        )
        rs = client.summarize_route(q)
        assert rs.flights.total_flights == 0
        assert rs.flights.on_time_rate == 0.0
        assert rs.flights.mean_departure_delay_min is None
        # by_cause should be None when there are no flights.
        assert rs.by_cause is None
        # Notable observation should explicitly say "no flights".
        assert any("No flights" in o for o in rs.notable_observations)

    def test_date_outside_range_returns_zero(self, client: DuckDBClient) -> None:
        q = RouteQuery(
            origin="ORD",
            dest="LGA",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        rs = client.summarize_route(q)
        assert rs.flights.total_flights == 0

    def test_reversed_date_window_raises(self, client: DuckDBClient) -> None:
        q = RouteQuery(
            origin="ORD",
            dest="LGA",
            start_date=date(2024, 7, 31),
            end_date=date(2024, 7, 1),
        )
        with pytest.raises(FlightDataError, match="Invalid date window"):
            client.summarize_route(q)

    def test_missing_origin_or_dest_raises(self, client: DuckDBClient) -> None:
        q = RouteQuery(
            origin="ORD",
            start_date=date(2024, 7, 1),
            end_date=date(2024, 7, 31),
        )
        with pytest.raises(FlightDataError, match="requires both"):
            client.summarize_route(q)


class TestTopRoutes:
    def test_top_routes_from_ord(self, client: DuckDBClient) -> None:
        routes = client.top_routes_from(
            origin="ORD",
            start_date="2024-07-01",
            end_date="2024-07-31",
            limit=5,
        )
        # Only one route out of ORD in the fixture.
        assert len(routes) == 1
        assert routes[0].dest == "LGA"
        assert routes[0].flights.total_flights == 90

    def test_top_routes_from_airport_with_no_flights_empty(self, client: DuckDBClient) -> None:
        routes = client.top_routes_from(
            origin="DEN",  # not present in fixture
            start_date="2024-07-01",
            end_date="2024-07-31",
        )
        assert routes == []


class TestNotableObservations:
    def test_low_on_time_rate_triggers_observation(self, client: DuckDBClient) -> None:
        q = RouteQuery(
            origin="ORD",
            dest="LGA",
            start_date=date(2024, 7, 1),
            end_date=date(2024, 7, 31),
        )
        rs = client.summarize_route(q)
        # ORD->LGA in fixture has 30/90 on-time => ~33%, well below 65% threshold
        assert any("below the industry baseline" in o for o in rs.notable_observations)

    def test_dominant_delay_cause_surfaced(self, client: DuckDBClient) -> None:
        q = RouteQuery(
            origin="SFO",
            dest="SEA",
            start_date=date(2024, 7, 1),
            end_date=date(2024, 7, 31),
        )
        rs = client.summarize_route(q)
        # SFO->SEA fixture: 28 min late_aircraft per flight
        assert rs.by_cause is not None
        assert rs.by_cause.late_aircraft_min == pytest.approx(28.0)
        assert any("late aircraft" in o.lower() for o in rs.notable_observations)
