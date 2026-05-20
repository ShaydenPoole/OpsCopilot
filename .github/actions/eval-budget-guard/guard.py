"""Eval budget guard — gate CI eval runs on month-to-date OpenRouter spend.

Reads ``evals/budget.json`` (relative to the repo root / workflow CWD) and
writes ``allowed``, ``month_to_date``, and ``cap`` to ``$GITHUB_OUTPUT``.

This script is **read-only**: it never mutates ``budget.json``. The
``eval-full`` workflow owns the spend write-back and the month-boundary reset.
If the recorded month is stale (a new month has started since the last
write-back), month-to-date is treated as ``0`` so a new month always starts
unblocked.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

BUDGET_PATH = Path("evals/budget.json")


def main() -> int:
    if not BUDGET_PATH.exists():
        _fail(f"{BUDGET_PATH} not found — cannot evaluate the eval budget.")
        return 1

    try:
        budget = json.loads(BUDGET_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _fail(f"{BUDGET_PATH} is not valid JSON: {exc}")
        return 1

    current_month = datetime.now(UTC).strftime("%Y-%m")
    recorded_month = budget.get("month")
    # Stale month → this is the first run of a new month; spend resets to 0.
    spent = 0.0 if recorded_month != current_month else float(budget.get("spent_usd", 0.0))
    cap = float(budget.get("cap_usd", 20.0))
    allowed = spent < cap

    _emit("allowed", "true" if allowed else "false")
    _emit("month_to_date", f"{spent:.2f}")
    _emit("cap", f"{cap:.2f}")

    if allowed:
        print(f"Eval budget OK — ${spent:.2f} of ${cap:.2f} used this month ({current_month}).")
    else:
        print(
            f"::warning title=Eval budget exceeded::${spent:.2f} of ${cap:.2f} used this "
            f"month ({current_month}). The eval will be skipped. Raise cap_usd in "
            f"evals/budget.json (or wait for the month boundary) to resume."
        )
    # The guard itself always succeeds — the workflow gates eval steps on the
    # `allowed` output rather than on this script's exit code.
    return 0


def _emit(key: str, value: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")
    else:  # local invocation — print so it is still inspectable
        print(f"{key}={value}")


def _fail(message: str) -> None:
    print(f"::error title=Eval budget guard::{message}")


if __name__ == "__main__":
    sys.exit(main())
