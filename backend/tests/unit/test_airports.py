"""Tests for the top-50 airport constant and helpers."""

from __future__ import annotations

from aviation_copilot.data.airports import (
    TOP_50_AIRPORTS,
    airport_name,
    iata_to_icao,
    icao_to_iata,
    is_top_50,
)


class TestTopFiftyConstants:
    def test_set_has_exactly_fifty_airports(self) -> None:
        assert len(TOP_50_AIRPORTS) == 50

    def test_all_iata_codes_are_three_chars(self) -> None:
        for iata in TOP_50_AIRPORTS:
            assert len(iata) == 3
            assert iata.isupper()

    def test_all_icao_codes_are_four_chars(self) -> None:
        for icao, _ in TOP_50_AIRPORTS.values():
            assert len(icao) == 4
            assert icao.isupper()

    def test_no_duplicate_icao(self) -> None:
        icaos = [icao for icao, _ in TOP_50_AIRPORTS.values()]
        assert len(icaos) == len(set(icaos))

    def test_anchor_airports_present(self) -> None:
        for iata in ("ORD", "JFK", "LAX", "ATL", "SFO"):
            assert iata in TOP_50_AIRPORTS


class TestIsTopFifty:
    def test_iata_match(self) -> None:
        assert is_top_50("ORD")
        assert is_top_50("ord")  # case-insensitive

    def test_icao_match(self) -> None:
        assert is_top_50("KORD")
        assert is_top_50("kord")

    def test_unknown_returns_false(self) -> None:
        assert not is_top_50("XYZ")
        assert not is_top_50("KXYZ")

    def test_empty_returns_false(self) -> None:
        assert not is_top_50("")


class TestCodeConversion:
    def test_iata_to_icao_known(self) -> None:
        assert iata_to_icao("ORD") == "KORD"
        assert iata_to_icao("HNL") == "PHNL"  # Honolulu has P prefix

    def test_iata_to_icao_unknown(self) -> None:
        assert iata_to_icao("XYZ") is None

    def test_icao_to_iata_known(self) -> None:
        assert icao_to_iata("KORD") == "ORD"
        assert icao_to_iata("kord") == "ORD"

    def test_icao_to_iata_unknown(self) -> None:
        assert icao_to_iata("KXYZ") is None

    def test_airport_name_resolves_for_iata_or_icao(self) -> None:
        assert airport_name("ORD") is not None
        assert airport_name("KORD") == airport_name("ORD")
        assert airport_name("XYZ") is None
