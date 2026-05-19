"""Top 50 US airports by passenger volume.

Source: FAA CY2023 enplanement rankings, intersected with airports present in
BTS On-Time Performance data. Hardcoded as a constant because the set is stable
year-over-year and the project does not need a dynamic airport directory.
"""

from __future__ import annotations

# IATA -> (ICAO, common name) for the top 50 US airports by passenger volume.
# Ordered by 2023 enplanements (highest first).
TOP_50_AIRPORTS: dict[str, tuple[str, str]] = {
    "ATL": ("KATL", "Hartsfield-Jackson Atlanta International"),
    "DFW": ("KDFW", "Dallas/Fort Worth International"),
    "DEN": ("KDEN", "Denver International"),
    "ORD": ("KORD", "Chicago O'Hare International"),
    "LAX": ("KLAX", "Los Angeles International"),
    "JFK": ("KJFK", "John F. Kennedy International"),
    "LAS": ("KLAS", "Harry Reid International (Las Vegas)"),
    "MCO": ("KMCO", "Orlando International"),
    "MIA": ("KMIA", "Miami International"),
    "CLT": ("KCLT", "Charlotte Douglas International"),
    "SEA": ("KSEA", "Seattle-Tacoma International"),
    "PHX": ("KPHX", "Phoenix Sky Harbor International"),
    "EWR": ("KEWR", "Newark Liberty International"),
    "SFO": ("KSFO", "San Francisco International"),
    "IAH": ("KIAH", "George Bush Intercontinental (Houston)"),
    "BOS": ("KBOS", "Boston Logan International"),
    "FLL": ("KFLL", "Fort Lauderdale-Hollywood International"),
    "MSP": ("KMSP", "Minneapolis-Saint Paul International"),
    "LGA": ("KLGA", "LaGuardia"),
    "DTW": ("KDTW", "Detroit Metropolitan Wayne County"),
    "PHL": ("KPHL", "Philadelphia International"),
    "SLC": ("KSLC", "Salt Lake City International"),
    "BWI": ("KBWI", "Baltimore/Washington International Thurgood Marshall"),
    "DCA": ("KDCA", "Ronald Reagan Washington National"),
    "SAN": ("KSAN", "San Diego International"),
    "IAD": ("KIAD", "Washington Dulles International"),
    "TPA": ("KTPA", "Tampa International"),
    "MDW": ("KMDW", "Chicago Midway International"),
    "AUS": ("KAUS", "Austin-Bergstrom International"),
    "BNA": ("KBNA", "Nashville International"),
    "HNL": ("PHNL", "Daniel K. Inouye International (Honolulu)"),
    "DAL": ("KDAL", "Dallas Love Field"),
    "RDU": ("KRDU", "Raleigh-Durham International"),
    "STL": ("KSTL", "St. Louis Lambert International"),
    "HOU": ("KHOU", "William P. Hobby (Houston)"),
    "PDX": ("KPDX", "Portland International"),
    "OAK": ("KOAK", "Oakland International"),
    "SMF": ("KSMF", "Sacramento International"),
    "MSY": ("KMSY", "Louis Armstrong New Orleans International"),
    "SJC": ("KSJC", "Norman Y. Mineta San Jose International"),
    "SAT": ("KSAT", "San Antonio International"),
    "PIT": ("KPIT", "Pittsburgh International"),
    "RSW": ("KRSW", "Southwest Florida International (Fort Myers)"),
    "CLE": ("KCLE", "Cleveland Hopkins International"),
    "IND": ("KIND", "Indianapolis International"),
    "CVG": ("KCVG", "Cincinnati/Northern Kentucky International"),
    "MKE": ("KMKE", "Milwaukee Mitchell International"),
    "JAX": ("KJAX", "Jacksonville International"),
    "CMH": ("KCMH", "John Glenn Columbus International"),
    "ANC": ("PANC", "Ted Stevens Anchorage International"),
}

# Set forms for fast membership checks.
_IATA_SET = frozenset(TOP_50_AIRPORTS.keys())
_ICAO_SET = frozenset(icao for icao, _ in TOP_50_AIRPORTS.values())


def is_top_50(code: str) -> bool:
    """Return True if ``code`` is one of the top 50 US airports.

    Accepts either IATA (3 chars, e.g. ``"ORD"``) or ICAO (4 chars, e.g.
    ``"KORD"``) codes. Case-insensitive.
    """
    if not code:
        return False
    upper = code.upper()
    return upper in _IATA_SET or upper in _ICAO_SET


def iata_to_icao(iata: str) -> str | None:
    """Return the ICAO code for a top-50 IATA, or None if not in the set."""
    entry = TOP_50_AIRPORTS.get(iata.upper())
    return entry[0] if entry else None


def icao_to_iata(icao: str) -> str | None:
    """Return the IATA code for a top-50 ICAO, or None if not in the set."""
    upper = icao.upper()
    for iata, (canonical_icao, _) in TOP_50_AIRPORTS.items():
        if canonical_icao == upper:
            return iata
    return None


def airport_name(code: str) -> str | None:
    """Return the human-readable airport name for a top-50 code (IATA or ICAO)."""
    upper = code.upper()
    entry = TOP_50_AIRPORTS.get(upper)
    if entry:
        return entry[1]
    for icao, name in TOP_50_AIRPORTS.values():
        if icao == upper:
            return name
    return None
