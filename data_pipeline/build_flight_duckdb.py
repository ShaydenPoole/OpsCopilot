"""Transform downloaded BTS CSVs into a single DuckDB file.

Reads every CSV under ``data/raw/bts_otp/``, filters to flights where BOTH
origin and destination are in :data:`aviation_copilot.data.airports.TOP_50_AIRPORTS`,
and writes the result to ``data/flights.duckdb`` (default).

The BTS schema is wide and includes many columns we don't use. This script
selects only the columns the agent actually queries (see
``aviation_copilot.data.duckdb_client`` for the canonical column list).

Usage:
    uv run python data_pipeline/build_flight_duckdb.py
    uv run python data_pipeline/build_flight_duckdb.py --verify   # run probe queries
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / "data" / "raw" / "bts_otp"
DEFAULT_OUT = ROOT / "data" / "flights.duckdb"
DEFAULT_VERSION = ROOT / "data" / "data_version.json"

# BTS column names → normalized column names used by the agent.
# BTS occasionally renames columns between schema revisions; this map is the
# single source of truth and should be kept in sync with the live header.
BTS_COLUMNS = {
    "FlightDate": "flight_date",
    "Origin": "origin_iata",
    "Dest": "dest_iata",
    "Reporting_Airline": "airline_iata",
    "Flight_Number_Reporting_Airline": "flight_number",
    "CRSDepTime": "scheduled_dep_time_int",
    "CRSArrTime": "scheduled_arr_time_int",
    "DepDelayMinutes": "departure_delay_min",
    "ArrDelayMinutes": "arrival_delay_min",
    "Cancelled": "cancelled_raw",
    "Diverted": "diverted_raw",
    "CarrierDelay": "carrier_delay_min",
    "WeatherDelay": "weather_delay_min",
    "NASDelay": "nas_delay_min",
    "SecurityDelay": "security_delay_min",
    "LateAircraftDelay": "late_aircraft_min",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build the flights DuckDB from raw CSVs.")
    p.add_argument("--in", dest="in_dir", type=Path, default=DEFAULT_IN, help="Input directory.")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output DuckDB path.")
    p.add_argument(
        "--version-file",
        type=Path,
        default=DEFAULT_VERSION,
        help="Path to write the data_version.json manifest.",
    )
    p.add_argument(
        "--verify",
        action="store_true",
        help="After building, run a small probe-query suite and exit non-zero on failure.",
    )
    return p.parse_args()


def discover_csvs(in_dir: Path) -> list[Path]:
    csvs = sorted(in_dir.glob("bts_otp_*.csv"))
    if not csvs:
        raise SystemExit(
            f"No BTS CSVs found under {in_dir}. Run download_bts_otp.py first."
        )
    return csvs


def build_duckdb(csvs: list[Path], out: Path) -> dict[str, object]:
    """Build the DuckDB file in a single CREATE TABLE AS query.

    Returns a stats dict for the version manifest.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    # Lazy import of the top-50 set so this script is independent of the
    # backend package layout when run as a standalone tool.
    from aviation_copilot.data.airports import TOP_50_AIRPORTS

    iatas = sorted(TOP_50_AIRPORTS.keys())
    iata_list_sql = ", ".join(f"'{c}'" for c in iatas)

    select_cols = """
        TRY_CAST(FlightDate AS DATE)                        AS flight_date,
        UPPER(Origin)                                       AS origin_iata,
        UPPER(Dest)                                         AS dest_iata,
        UPPER(Reporting_Airline)                            AS airline_iata,
        TRY_CAST(Flight_Number_Reporting_Airline AS INT)    AS flight_number,
        CRSDepTime                                          AS scheduled_dep_time_int,
        CRSArrTime                                          AS scheduled_arr_time_int,
        TRY_CAST(DepDelayMinutes AS DOUBLE)                 AS departure_delay_min,
        TRY_CAST(ArrDelayMinutes AS DOUBLE)                 AS arrival_delay_min,
        (TRY_CAST(Cancelled AS DOUBLE) > 0)                 AS cancelled,
        (TRY_CAST(Diverted AS DOUBLE) > 0)                  AS diverted,
        TRY_CAST(CarrierDelay AS DOUBLE)                    AS carrier_delay_min,
        TRY_CAST(WeatherDelay AS DOUBLE)                    AS weather_delay_min,
        TRY_CAST(NASDelay AS DOUBLE)                        AS nas_delay_min,
        TRY_CAST(SecurityDelay AS DOUBLE)                   AS security_delay_min,
        TRY_CAST(LateAircraftDelay AS DOUBLE)               AS late_aircraft_min
    """

    file_list = ", ".join(f"'{p.as_posix()}'" for p in csvs)

    print(f"Building {out} from {len(csvs)} CSV files...", file=sys.stderr)
    con = duckdb.connect(str(out))
    try:
        con.execute(
            f"""
            CREATE TABLE flights AS
            SELECT {select_cols}
            FROM read_csv_auto(
                [{file_list}],
                union_by_name=true,
                header=true,
                ignore_errors=true
            )
            WHERE UPPER(Origin) IN ({iata_list_sql})
              AND UPPER(Dest) IN ({iata_list_sql})
              AND TRY_CAST(FlightDate AS DATE) IS NOT NULL
            """
        )
        con.execute("CREATE INDEX idx_flights_route_date ON flights(origin_iata, dest_iata, flight_date)")
        con.execute("CREATE INDEX idx_flights_origin_date ON flights(origin_iata, flight_date)")
        con.execute("CREATE INDEX idx_flights_date ON flights(flight_date)")

        row_count = con.execute("SELECT COUNT(*) FROM flights").fetchone()
        date_range = con.execute(
            "SELECT MIN(flight_date), MAX(flight_date) FROM flights"
        ).fetchone()
    finally:
        con.close()

    return {
        "row_count": int(row_count[0]) if row_count else 0,
        "date_min": str(date_range[0]) if date_range and date_range[0] else None,
        "date_max": str(date_range[1]) if date_range and date_range[1] else None,
        "airport_count": len(iatas),
        "source_csvs": [c.name for c in csvs],
        "built_at": datetime.now(timezone.utc).isoformat(),
    }


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_version(version_file: Path, out: Path, stats: dict[str, object]) -> None:
    manifest = {
        **stats,
        "duckdb_sha256": file_sha256(out),
        "duckdb_path": str(out.relative_to(out.parents[1])) if out.is_absolute() else str(out),
        "duckdb_size_mb": round(out.stat().st_size / 1024 / 1024, 1),
    }
    version_file.parent.mkdir(parents=True, exist_ok=True)
    version_file.write_text(json.dumps(manifest, indent=2) + "\n")


def verify(out: Path) -> bool:
    """Run a small probe-query suite. Returns True on success."""
    print("Running probe queries...", file=sys.stderr)
    con = duckdb.connect(str(out), read_only=True)
    try:
        ord_count = con.execute(
            "SELECT COUNT(*) FROM flights WHERE origin_iata='ORD' AND dest_iata='LGA'"
        ).fetchone()
        avg_delay = con.execute(
            """
            SELECT AVG(departure_delay_min) FROM flights
            WHERE origin_iata='ORD' AND NOT cancelled
            """
        ).fetchone()
    finally:
        con.close()

    if not ord_count or not avg_delay:
        print("Probe query failed: empty result.", file=sys.stderr)
        return False
    ord_lga = int(ord_count[0])
    delay = float(avg_delay[0] or 0)
    print(f"  ORD -> LGA flights: {ord_lga}", file=sys.stderr)
    print(f"  ORD avg dep delay (min): {delay:.2f}", file=sys.stderr)
    if ord_lga == 0:
        print("Suspicious: zero ORD->LGA flights. Check input data.", file=sys.stderr)
        return False
    return True


def main() -> int:
    args = parse_args()
    csvs = discover_csvs(args.in_dir)
    stats = build_duckdb(csvs, args.out)
    write_version(args.version_file, args.out, stats)
    print(
        f"\nBuilt {args.out} — {stats['row_count']:,} rows from "
        f"{stats['date_min']} to {stats['date_max']}.",
        file=sys.stderr,
    )
    if args.verify and not verify(args.out):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
