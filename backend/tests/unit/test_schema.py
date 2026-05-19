"""Tests for the RouteQuery / FlightSummary / RouteSummary models."""

from __future__ import annotations

from datetime import date

import pytest
from aviation_copilot.data.schema import (
    DelayCauseSummary,
    FlightSummary,
    RouteQuery,
    RouteSummary,
)
from pydantic import ValidationError


class TestRouteQuery:
    def test_minimal_valid_query(self) -> None:
        q = RouteQuery(
            origin="ORD",
            dest="LGA",
            start_date=date(2024, 7, 1),
            end_date=date(2024, 7, 31),
        )
        assert q.origin == "ORD"
        assert q.dest == "LGA"
        assert q.airline is None

    def test_codes_uppercased(self) -> None:
        q = RouteQuery(
            origin="ord",
            dest="lga",
            airline="aa",
            start_date=date(2024, 7, 1),
            end_date=date(2024, 7, 31),
        )
        assert q.origin == "ORD"
        assert q.dest == "LGA"
        assert q.airline == "AA"

    def test_date_window_validation_ok(self) -> None:
        q = RouteQuery(
            origin="ORD",
            dest="LGA",
            start_date=date(2024, 7, 1),
            end_date=date(2024, 7, 31),
        )
        assert q.is_date_window_valid()

    def test_date_window_validation_fails_when_reversed(self) -> None:
        q = RouteQuery(
            origin="ORD",
            dest="LGA",
            start_date=date(2024, 7, 31),
            end_date=date(2024, 7, 1),
        )
        assert not q.is_date_window_valid()

    def test_oversized_origin_rejected(self) -> None:
        # IATA = 3, ICAO = 4. Anything longer is invalid input.
        with pytest.raises(ValidationError):
            RouteQuery(
                origin="ORDXX",
                dest="LGA",
                start_date=date(2024, 7, 1),
                end_date=date(2024, 7, 31),
            )

    def test_origin_and_dest_optional(self) -> None:
        # System-wide queries omit both.
        q = RouteQuery(
            start_date=date(2024, 7, 1),
            end_date=date(2024, 7, 31),
        )
        assert q.origin is None
        assert q.dest is None


class TestFlightSummary:
    def test_zero_flights_is_valid(self) -> None:
        s = FlightSummary(
            total_flights=0,
            cancelled=0,
            diverted=0,
            on_time_arrivals=0,
            on_time_rate=0.0,
        )
        assert s.total_flights == 0
        assert s.mean_departure_delay_min is None

    def test_negative_counts_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FlightSummary(
                total_flights=-1,
                cancelled=0,
                diverted=0,
                on_time_arrivals=0,
                on_time_rate=0.0,
            )

    def test_on_time_rate_bounded(self) -> None:
        with pytest.raises(ValidationError):
            FlightSummary(
                total_flights=10,
                cancelled=0,
                diverted=0,
                on_time_arrivals=11,  # impossible
                on_time_rate=1.1,  # out of bounds
            )


class TestRouteSummary:
    def test_round_trip(self) -> None:
        rs = RouteSummary(
            origin="ORD",
            dest="LGA",
            flights=FlightSummary(
                total_flights=90,
                cancelled=2,
                diverted=0,
                on_time_arrivals=75,
                on_time_rate=75 / 90,
                mean_departure_delay_min=8.4,
                mean_arrival_delay_min=10.1,
            ),
            by_cause=DelayCauseSummary(
                carrier_min=1.2,
                weather_min=4.8,
                nas_min=2.1,
                security_min=0.0,
                late_aircraft_min=3.0,
            ),
        )
        payload = rs.model_dump_json()
        rt = RouteSummary.model_validate_json(payload)
        assert rt.origin == "ORD"
        assert rt.flights.total_flights == 90
        assert rt.by_cause is not None
        assert rt.by_cause.weather_min == pytest.approx(4.8)
