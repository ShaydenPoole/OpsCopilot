"""Download BTS On-Time Performance monthly ZIPs.

Source: https://www.transtats.bts.gov/PREZIP/
Files are named ``On_Time_Reporting_Carrier_On_Time_Performance_1987_present_<YEAR>_<MONTH>.zip``
and each contains a single CSV with one row per scheduled flight.

This script downloads N months of data ending at a given month (default: last
month relative to today) and caches the unzipped CSVs under
``data/raw/bts_otp/``. Already-downloaded months are skipped.

Usage:
    uv run python data_pipeline/download_bts_otp.py --years 2
    uv run python data_pipeline/download_bts_otp.py --start 2024-01 --end 2025-12

The output is consumed by ``build_flight_duckdb.py`` (U2).
"""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
from datetime import date
from pathlib import Path

import httpx

BTS_BASE_URL = (
    "https://www.transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
)
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "bts_otp"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download BTS OTP monthly archives.")
    p.add_argument("--years", type=int, default=2, help="Number of years to download, ending last month.")
    p.add_argument("--start", type=str, help="Start month, YYYY-MM. Overrides --years.")
    p.add_argument("--end", type=str, help="End month, YYYY-MM. Overrides --years.")
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Output directory for unzipped CSVs.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the URLs that would be fetched, but do not download.",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="HTTP timeout per request, in seconds.",
    )
    return p.parse_args()


def month_range(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    y, m = start
    while (y, m) <= end:
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def resolve_window(args: argparse.Namespace) -> list[tuple[int, int]]:
    if args.start and args.end:
        s = tuple(int(x) for x in args.start.split("-"))
        e = tuple(int(x) for x in args.end.split("-"))
        if len(s) != 2 or len(e) != 2:
            raise SystemExit("--start and --end must be YYYY-MM.")
        return month_range((s[0], s[1]), (e[0], e[1]))

    today = date.today()
    end_y, end_m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    start_y = end_y - args.years
    start_m = end_m + 1
    if start_m > 12:
        start_m = 1
        start_y += 1
    return month_range((start_y, start_m), (end_y, end_m))


def download_month(client: httpx.Client, year: int, month: int, out_dir: Path) -> Path | None:
    """Download one month, unzip the single CSV, return its path. Skip if cached."""
    target = out_dir / f"bts_otp_{year}_{month:02d}.csv"
    if target.exists():
        print(f"[skip] {target.name} already present.", file=sys.stderr)
        return target

    url = BTS_BASE_URL.format(year=year, month=month)
    print(f"[fetch] {year}-{month:02d} <- {url}", file=sys.stderr)
    try:
        resp = client.get(url, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"[error] {year}-{month:02d}: {exc}", file=sys.stderr)
        return None

    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_names:
                print(f"[error] {year}-{month:02d}: no CSV inside zip.", file=sys.stderr)
                return None
            inner = csv_names[0]
            data = zf.read(inner)
    except zipfile.BadZipFile as exc:
        print(f"[error] {year}-{month:02d}: bad zip — {exc}", file=sys.stderr)
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    size_mb = target.stat().st_size / 1024 / 1024
    print(f"[done]  {target.name} ({size_mb:.1f} MB)", file=sys.stderr)
    return target


def main() -> int:
    args = parse_args()
    months = resolve_window(args)
    print(
        f"Window: {months[0][0]}-{months[0][1]:02d} → {months[-1][0]}-{months[-1][1]:02d} "
        f"({len(months)} months)",
        file=sys.stderr,
    )

    if args.dry_run:
        for y, m in months:
            print(BTS_BASE_URL.format(year=y, month=m))
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    failed: list[tuple[int, int]] = []
    with httpx.Client(timeout=args.timeout) as client:
        for y, m in months:
            if download_month(client, y, m, args.out) is None:
                failed.append((y, m))

    if failed:
        print(f"\n{len(failed)} months failed: {failed}", file=sys.stderr)
        return 1
    print(f"\nAll {len(months)} months downloaded to {args.out}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
