"""Inspect AI solver that runs our agent end-to-end.

The solver:

1. Builds an agent against the configured model (env-controlled).
2. Runs ``run_with_trace`` for the sample's question.
3. Stashes the structured trace + any retrieved chunk_ids into
   ``state.metadata`` so the scorers can read them.
4. Returns the agent's answer as ``state.output``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aviation_copilot.agent.core import (
    AgentDeps,
    build_agent,
    clear_tool_registrars,
    run_with_trace,
)
from aviation_copilot.agent.trace import Trace
from aviation_copilot.config import get_settings

if TYPE_CHECKING:
    from inspect_ai.solver import TaskState


def aviation_agent_solver():  # noqa: ANN201
    """Return an Inspect AI Solver bound to the configured agent."""
    from inspect_ai.model import ChatMessageAssistant
    from inspect_ai.solver import Generate, solver

    settings = get_settings()

    # Build a single agent instance reused across samples in the run for
    # connection reuse and lower per-question latency. Tool registrars
    # are registered once.
    clear_tool_registrars()
    from aviation_copilot.tools import register_default_registrars

    register_default_registrars()
    agent = build_agent(settings=settings, apply_tool_registrars=True)

    @solver
    def _solver():  # noqa: ANN202
        async def solve(state: TaskState, generate: Generate) -> TaskState:
            metadata = dict(state.metadata or {})
            question = metadata.get("question") or state.input_text

            deps = AgentDeps(trace=Trace.new(question=question))
            result = await run_with_trace(
                question,
                agent=agent,
                deps=deps,
                settings=settings,
            )
            # Stash structured artifacts for the scorers.
            metadata["trace"] = result.trace.model_dump(mode="json")
            metadata["agent_error"] = result.error
            state.metadata = metadata
            # Inspect AI reads state.output.completion for scoring.
            state.output.completion = result.answer
            state.messages.append(ChatMessageAssistant(content=result.answer))
            return state

        return solve

    return _solver()
