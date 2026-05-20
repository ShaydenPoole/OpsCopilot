"""Render the eval headline metrics as an SVG table for the README.

Reads the JSON written by ``evals/summarize.py`` (``evals/results/latest.json``)
and writes a self-contained SVG. The ``eval-full`` CI workflow runs this after
every full eval and commits the SVG, so the README badge stays current.

Stdlib only — no dependencies, runs anywhere.

Usage:
    python scripts/generate_eval_table.py evals/results/latest.json docs/images/eval-results-table.svg
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Target thresholds from the plan's Success Metrics. A metric at or above its
# threshold renders green; below renders amber. Metrics not listed render neutral.
THRESHOLDS: dict[str, float] = {
    "tool_call_accuracy": 0.85,
    "retrieval_recall_at_5": 0.75,
    "judge_score_mean": 0.75,
}

# Palette — matches the frontend's dark slate + teal theme.
BG = "#0f172a"
PANEL = "#1e293b"
TEXT = "#e2e8f0"
MUTED = "#94a3b8"
ACCENT = "#2dd4bf"
GREEN = "#34d399"
AMBER = "#fbbf24"

ROW_H = 38
HEADER_H = 64
PAD = 24
WIDTH = 560


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _load_headline(json_path: Path) -> dict[str, Any]:
    if not json_path.exists():
        return {}
    try:
        # utf-8-sig tolerates a leading BOM if the file was written by an
        # editor that adds one.
        data = json.loads(json_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}
    headline = data.get("headline")
    return headline if isinstance(headline, dict) else {}


def _row_color(name: str, value: Any) -> str:
    threshold = THRESHOLDS.get(name)
    if threshold is None or not isinstance(value, (int, float)):
        return MUTED
    return GREEN if value >= threshold else AMBER


def render_svg(headline: dict[str, Any]) -> str:
    rows = list(headline.items())
    body_h = ROW_H * max(len(rows), 1)
    height = HEADER_H + body_h + PAD

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}" font-family="ui-sans-serif,system-ui,sans-serif">',
        f'<rect width="{WIDTH}" height="{height}" rx="12" fill="{BG}"/>',
        f'<text x="{PAD}" y="36" fill="{TEXT}" font-size="18" font-weight="700">'
        f"Eval suite results</text>",
        f'<text x="{PAD}" y="54" fill="{MUTED}" font-size="12">'
        f"Inspect AI · refreshed by CI on every push to main</text>",
    ]

    if not rows:
        parts.append(
            f'<text x="{PAD}" y="{HEADER_H + 28}" fill="{MUTED}" font-size="13">'
            f"Pending the first eval-full CI run.</text>"
        )
    else:
        for i, (name, value) in enumerate(rows):
            y = HEADER_H + i * ROW_H
            color = _row_color(name, value)
            shown = f"{value:.3f}" if isinstance(value, (int, float)) else str(value)
            if i % 2 == 0:
                parts.append(
                    f'<rect x="{PAD - 8}" y="{y}" width="{WIDTH - 2 * (PAD - 8)}" '
                    f'height="{ROW_H}" rx="6" fill="{PANEL}"/>'
                )
            parts.append(
                f'<circle cx="{PAD + 5}" cy="{y + ROW_H // 2}" r="5" fill="{color}"/>'
            )
            parts.append(
                f'<text x="{PAD + 22}" y="{y + ROW_H // 2 + 5}" fill="{TEXT}" '
                f'font-size="14">{_escape(name)}</text>'
            )
            parts.append(
                f'<text x="{WIDTH - PAD}" y="{y + ROW_H // 2 + 5}" fill="{color}" '
                f'font-size="14" font-weight="700" text-anchor="end">{_escape(shown)}</text>'
            )

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    json_path, svg_path = Path(argv[1]), Path(argv[2])
    headline = _load_headline(json_path)
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(render_svg(headline), encoding="utf-8")
    state = f"{len(headline)} metric(s)" if headline else "placeholder (no results yet)"
    print(f"Wrote {svg_path} — {state}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
