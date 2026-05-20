"""Retrieval-quality scorer.

For questions with labeled ``expected_retrieval_chunk_ids``, compute
recall@k of the agent's corpus_search invocations. Score = intersection
size / expected size, scaled to [0.0, 1.0].

Questions without expected chunks skip the scorer (NOANSWER) so the
aggregate metric only reflects RAG-flavored questions.
"""

from __future__ import annotations

from aviation_copilot.agent.trace import Trace, ToolResultStep


def score_retrieval(
    *,
    expected_chunk_ids: list[str],
    trace: Trace,
) -> tuple[float | None, str]:
    if not expected_chunk_ids:
        return None, "No expected_retrieval_chunk_ids; scorer not applicable."

    retrieved: set[str] = set()
    for step in trace.steps:
        if not isinstance(step, ToolResultStep) or step.tool_name != "corpus_search":
            continue
        # The trace records only a preview; full chunk_ids live on the
        # tool's structured output, which the solver attaches to metadata
        # under "corpus_chunk_ids".
        retrieved.update(_chunk_ids_from_preview(step.result_preview))

    expected_set = set(expected_chunk_ids)
    hit = retrieved & expected_set
    recall = len(hit) / len(expected_set) if expected_set else 0.0
    explanation = (
        f"recall = {len(hit)}/{len(expected_set)} = {recall:.2f} "
        f"(expected: {sorted(expected_set)[:3]}{'...' if len(expected_set) > 3 else ''})"
    )
    return recall, explanation


def _chunk_ids_from_preview(preview: str) -> set[str]:
    """Best-effort chunk_id extraction from a result_preview string.

    Real chunk_ids look like ``aim_chap4::airspace::0007`` — alphanumeric
    plus ``::`` separators. We extract anything matching that pattern.
    """
    import re

    return set(re.findall(r"[a-z0-9_]+::[a-z0-9_-]+::\d+", preview))


def retrieval_quality_scorer():  # noqa: ANN201
    from inspect_ai.scorer import NOANSWER, Score, Target, mean, scorer
    from inspect_ai.solver import TaskState

    @scorer(metrics=[mean()])
    def _scorer():  # noqa: ANN202
        async def score(state: TaskState, target: Target) -> Score:
            metadata = state.metadata or {}
            trace = _trace_from_state(state)
            value, explanation = score_retrieval(
                expected_chunk_ids=metadata.get("expected_retrieval_chunk_ids", []),
                trace=trace,
            )
            if value is None:
                return Score(value=NOANSWER, explanation=explanation)
            return Score(value=value, explanation=explanation)

        return score

    return _scorer()


def _trace_from_state(state) -> Trace:  # noqa: ANN001
    raw = (state.metadata or {}).get("trace")
    if raw is None:
        return Trace.new()
    if isinstance(raw, Trace):
        return raw
    return Trace.model_validate(raw)
