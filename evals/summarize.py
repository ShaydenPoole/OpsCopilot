"""Summarize an Inspect AI eval run into JSON + Markdown.

Inspect writes per-run ``.eval`` logs to a ``--log-dir``. This script reads the
most recent log in that directory and emits:

- a JSON file (``--json-out``) — every scorer/metric, plus a flat ``headline``
  map; consumed by the README badge generator (``scripts/generate_eval_table.py``)
  and committed to ``evals/results/latest.json`` by the eval-full workflow;
- a Markdown table on **stdout** — posted as a PR comment by the eval-smoke
  workflow.

Progress and errors go to stderr so stdout stays clean for redirection.

Usage:
    python evals/summarize.py <log-dir> --json-out evals/results/latest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def _load_latest_log(log_dir: Path) -> Any | None:
    """Return the most recently created EvalLog in ``log_dir``, or None."""
    from inspect_ai.log import list_eval_logs, read_eval_log

    infos = list_eval_logs(str(log_dir))
    if not infos:
        return None
    logs = [read_eval_log(info) for info in infos]
    logs.sort(key=lambda log: getattr(log.eval, "created", "") or "")
    return logs[-1]


def summarize(log: Any) -> dict[str, Any]:
    """Flatten an EvalLog into a JSON-serializable summary."""
    results = getattr(log, "results", None)
    scores: dict[str, dict[str, float]] = {}
    headline: dict[str, float] = {}

    for score in getattr(results, "scores", []) or []:
        metrics = {
            metric.name: _round(metric.value) for metric in (score.metrics or {}).values()
        }
        scores[score.name] = metrics
        for metric_name, value in metrics.items():
            # Flat headline keyed by metric name; disambiguate on collision.
            key = metric_name if metric_name not in headline else f"{score.name}/{metric_name}"
            headline[key] = value

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": getattr(log, "status", "unknown"),
        "model": getattr(getattr(log, "eval", None), "model", "unknown"),
        "task": getattr(getattr(log, "eval", None), "task", "unknown"),
        "total_samples": getattr(results, "total_samples", 0) if results else 0,
        "completed_samples": getattr(results, "completed_samples", 0) if results else 0,
        "scores": scores,
        "headline": headline,
    }


def _round(value: Any) -> float:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return value


def to_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "### Eval results",
        "",
        f"- **Task:** `{summary['task']}`",
        f"- **Model:** `{summary['model']}`",
        f"- **Samples:** {summary['completed_samples']} / {summary['total_samples']}",
        f"- **Status:** {summary['status']}",
        "",
    ]
    if summary["headline"]:
        lines += ["| Metric | Value |", "| --- | --- |"]
        for name, value in summary["headline"].items():
            lines.append(f"| {name} | {value} |")
    else:
        lines.append("_No scored metrics found in the eval log._")
    lines += ["", f"_Generated {summary['generated_at']}._"]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize an Inspect AI eval run.")
    parser.add_argument("log_dir", type=Path, help="Directory of Inspect .eval logs")
    parser.add_argument("--json-out", type=Path, help="Write the JSON summary here")
    parser.add_argument("--md-out", type=Path, help="Write Markdown here instead of stdout")
    args = parser.parse_args()

    try:
        log = _load_latest_log(args.log_dir)
    except Exception as exc:  # noqa: BLE001 — summary must not crash the workflow
        _log(f"Failed to read eval logs from {args.log_dir}: {exc}")
        log = None

    if log is None:
        summary: dict[str, Any] = {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "status": "no-logs",
            "model": "unknown",
            "task": "unknown",
            "total_samples": 0,
            "completed_samples": 0,
            "scores": {},
            "headline": {},
        }
        _log(f"No eval logs found in {args.log_dir}.")
    else:
        summary = summarize(log)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        _log(f"Wrote JSON summary to {args.json_out}")

    markdown = to_markdown(summary)
    if args.md_out:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(markdown + "\n", encoding="utf-8")
        _log(f"Wrote Markdown summary to {args.md_out}")
    else:
        print(markdown)

    return 0


if __name__ == "__main__":
    sys.exit(main())
