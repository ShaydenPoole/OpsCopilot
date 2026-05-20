"""Inspect AI Task definition.

Run via:

    cd backend
    uv run --extra eval inspect eval ../evals/run_eval.py --model openrouter/openai/gpt-oss-120b

Outputs land in ``evals/results/`` per Inspect AI's default layout.
``--limit N`` runs a subset (used by CI eval-smoke).
"""

from __future__ import annotations

from inspect_ai import Task, task
from inspect_ai.dataset import Sample

from evals.dataset import EvalQuestion, load_question_bank
from evals.scorers import (
    llm_as_judge_scorer,
    retrieval_quality_scorer,
    security_redteam_scorer,
    tool_call_correctness_scorer,
)
from evals.solver import aviation_agent_solver


def _question_to_sample(q: EvalQuestion) -> Sample:
    return Sample(
        id=q.id,
        input=q.question,
        target="",  # No reference completion — scorers grade from trace + answer
        metadata=q.model_dump(mode="json"),
    )


@task
def aviation_ops_copilot_eval() -> Task:
    """Full eval suite — six question categories, four scorers."""
    questions = load_question_bank()
    samples = [_question_to_sample(q) for q in questions]
    return Task(
        dataset=samples,
        solver=aviation_agent_solver(),
        scorer=[
            tool_call_correctness_scorer(),
            retrieval_quality_scorer(),
            security_redteam_scorer(),
            llm_as_judge_scorer(),
        ],
    )


@task
def aviation_ops_copilot_smoke() -> Task:
    """Smoke subset (~10 questions) used by CI eval-smoke on PRs."""
    questions = load_question_bank()
    # Pick the first 2 from each category, capped at 12 total.
    by_category: dict[str, list[EvalQuestion]] = {}
    for q in questions:
        by_category.setdefault(q.category, []).append(q)
    smoke: list[EvalQuestion] = []
    for cat_qs in by_category.values():
        smoke.extend(cat_qs[:2])
    smoke = smoke[:12]
    return Task(
        dataset=[_question_to_sample(q) for q in smoke],
        solver=aviation_agent_solver(),
        scorer=[
            tool_call_correctness_scorer(),
            security_redteam_scorer(),
            llm_as_judge_scorer(),
        ],
    )
