"""Hydrate the Modal Volume (or local data/) with built artifacts.

When invoked with ``--local`` (or outside Modal), this script just confirms
both data artifacts exist under ``data/`` and prints their stats.

When invoked via Modal (``modal run data_pipeline/hydrate_volume.py``), the
Modal-specific entry point in U11 wraps this with Volume mount + commit logic.

Lands in skeleton form here (U2/U3). Full Modal integration lands in U11.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "data"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Inspect or hydrate data artifacts.")
    p.add_argument("--local", action="store_true", help="Inspect local data/ only (no Modal).")
    p.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    return p.parse_args()


def check_local(data_dir: Path) -> int:
    duckdb_path = data_dir / "flights.duckdb"
    corpus_path = data_dir / "corpus_index.lance"
    version_path = data_dir / "data_version.json"
    corpus_version_path = data_dir / "corpus_version.json"

    errs: list[str] = []
    if not duckdb_path.exists():
        errs.append(
            f"  ✗ {duckdb_path} — run data_pipeline/build_flight_duckdb.py to create."
        )
    if not corpus_path.exists():
        errs.append(
            f"  ✗ {corpus_path}/ — run data_pipeline/build_corpus_index.py to create."
        )
    if errs:
        print("Missing artifacts:", file=sys.stderr)
        for e in errs:
            print(e, file=sys.stderr)
        return 1

    print("Local data artifacts present:", file=sys.stderr)
    if version_path.exists():
        v = json.loads(version_path.read_text())
        print(
            f"  ✓ flights.duckdb — {v.get('row_count', '?'):,} rows, "
            f"{v.get('date_min', '?')} → {v.get('date_max', '?')}, "
            f"{v.get('duckdb_size_mb', '?')} MB",
            file=sys.stderr,
        )
    else:
        print(f"  ✓ {duckdb_path}", file=sys.stderr)
    if corpus_version_path.exists():
        cv = json.loads(corpus_version_path.read_text())
        print(
            f"  ✓ corpus_index.lance/ — {cv.get('chunk_count', '?')} chunks, "
            f"embed model: {cv.get('embedding_model', '?')}",
            file=sys.stderr,
        )
    else:
        print(f"  ✓ {corpus_path}/", file=sys.stderr)
    return 0


def main() -> int:
    args = parse_args()
    if args.local:
        return check_local(args.data_dir)
    # Full Modal-aware hydration lands in U11. Stub for now.
    print(
        "Modal-aware hydration is implemented in U11. For local hydration, "
        "run with --local.",
        file=sys.stderr,
    )
    return check_local(args.data_dir)


if __name__ == "__main__":
    raise SystemExit(main())
