"""Download the FAA Aeronautical Information Manual (AIM) HTML.

The AIM is published at faa.gov as a multi-chapter HTML document. This script
fetches chapters 1-7 (the core operational content) and writes the raw HTML
to ``data/raw/faa_aim/<chapter>.html`` for downstream chunking by
``build_corpus_index.py``.

Usage:
    uv run python data_pipeline/download_faa_aim.py
    uv run python data_pipeline/download_faa_aim.py --chapters 1,2,3,4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

# Stable FAA URL pattern for AIM chapters. The FAA occasionally renames the
# top-level directory; this constant is the single source of truth.
AIM_BASE = "https://www.faa.gov/air_traffic/publications/atpubs/aim_html"
AIM_CHAPTERS: dict[int, str] = {
    1: f"{AIM_BASE}/chap1.html",
    2: f"{AIM_BASE}/chap2.html",
    3: f"{AIM_BASE}/chap3.html",
    4: f"{AIM_BASE}/chap4.html",
    5: f"{AIM_BASE}/chap5.html",
    6: f"{AIM_BASE}/chap6.html",
    7: f"{AIM_BASE}/chap7.html",
}

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "raw" / "faa_aim"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download FAA AIM HTML chapters.")
    p.add_argument(
        "--chapters",
        type=str,
        default="1,2,3,4,5,6,7",
        help="Comma-separated chapter numbers to download.",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Output directory for chapter HTML files.",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP timeout per chapter, in seconds.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print URLs without downloading.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    chapters = [int(c.strip()) for c in args.chapters.split(",") if c.strip()]
    unknown = [c for c in chapters if c not in AIM_CHAPTERS]
    if unknown:
        print(f"Unknown chapters: {unknown}. Valid: {sorted(AIM_CHAPTERS)}", file=sys.stderr)
        return 1

    if args.dry_run:
        for c in chapters:
            print(AIM_CHAPTERS[c])
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    failed: list[int] = []
    with httpx.Client(
        timeout=args.timeout,
        headers={"User-Agent": "aviation-ops-copilot/0.1 (educational portfolio project)"},
    ) as client:
        for chapter in chapters:
            url = AIM_CHAPTERS[chapter]
            dest = args.out / f"aim_chap{chapter}.html"
            print(f"[fetch] AIM ch{chapter} <- {url}", file=sys.stderr)
            try:
                resp = client.get(url, follow_redirects=True)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                print(f"[error] ch{chapter}: {exc}", file=sys.stderr)
                failed.append(chapter)
                continue
            dest.write_bytes(resp.content)
            print(f"[done]  {dest.name} ({len(resp.content) / 1024:.1f} KB)", file=sys.stderr)

    if failed:
        print(f"\n{len(failed)} chapters failed: {failed}", file=sys.stderr)
        return 1
    print(f"\nDownloaded {len(chapters)} AIM chapters to {args.out}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
