"""Live smoke test — run the agent against the real OpenRouter model.

Unlike the unit tests (which use Pydantic-AI's deterministic TestModel),
this exercises the real configured model end-to-end: OpenRouter auth,
tool calling, the agent loop, and trace capture.

Usage:
    cd backend
    uv run python scripts/smoke_agent.py

Requires OPENROUTER_API_KEY in env or ../.env. Costs a few cents.
flight_data_query / corpus_search report "unavailable" unless the local
DuckDB / LanceDB artifacts have been hydrated — that's expected.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Windows consoles default to cp1252, which can't encode Unicode characters
# the LLM may emit (narrow no-break space, em dashes). Force UTF-8 output.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Flat-layout package: add backend/ to sys.path so `aviation_copilot` resolves
# when this script is run directly (the project is `package = false` for uv).
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from aviation_copilot.agent.core import AgentDeps, build_agent, run_with_trace
from aviation_copilot.agent.trace import Trace
from aviation_copilot.config import get_settings
from aviation_copilot.tools import register_default_registrars

SMOKE_QUESTIONS = [
    "What's the current METAR for KORD?",
    "Are there any active NOTAMs for KJFK right now?",
]


async def main() -> int:
    settings = get_settings()
    if not settings.openrouter_api_key:
        print("OPENROUTER_API_KEY not set. Add it to ../.env", file=sys.stderr)
        return 1
    if settings.test_mode:
        print("AVIATION_COPILOT_TEST_MODE is set — unset it for a live test.", file=sys.stderr)
        return 1

    print(f"Model: {settings.agent_model} via {settings.openrouter_base_url}\n")
    register_default_registrars()
    agent = build_agent(settings=settings, apply_tool_registrars=True)

    for question in SMOKE_QUESTIONS:
        print(f"=== Q: {question}")
        deps = AgentDeps(trace=Trace.new(question=question))
        result = await run_with_trace(question, agent=agent, deps=deps, settings=settings)
        print(f"--- Answer:\n{result.answer}\n")
        print(f"--- Tools called: {result.trace.tools_called()}")
        print(f"--- Trace steps: {len(result.trace.steps)} | error: {result.error}")
        print(
            f"--- Tokens: in={result.trace.total_input_tokens()} "
            f"out={result.trace.total_output_tokens()}\n"
        )

    print("Smoke test complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
