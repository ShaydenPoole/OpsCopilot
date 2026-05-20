"""``corpus_search`` tool — semantic search over the FAA AIM corpus (LanceDB).

Wraps :class:`aviation_copilot.corpus.index.CorpusIndex` (U3). Returns the
top-K chunks with similarity scores; the agent should use the returned
``source`` and ``section`` fields when citing retrieved content.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from aviation_copilot.agent.core import AgentDeps
from aviation_copilot.agent.errors import ToolError
from aviation_copilot.corpus.index import CorpusSearchHit, search_passage_subset
from aviation_copilot.tools._base import truncate_for_trace

TOOL_NAME = "corpus_search"
DEFAULT_TOP_K = 5
LOW_CONFIDENCE_THRESHOLD = 0.0
"""Score threshold below which retrieval is flagged low-confidence.

With BGE-small + cosine similarity, well-matched chunks score 0.4-0.8.
Negative scores indicate the query has no good match in the corpus.
"""


class CorpusHit(BaseModel):
    """Wire shape returned to the agent. Mirrors CorpusSearchHit."""

    chunk_id: str
    source: str
    section: str
    text: str
    score: float


class CorpusSearchResult(BaseModel):
    query: str
    hits: list[CorpusHit] = Field(default_factory=list)
    low_confidence: bool = False
    """True when no hit cleared the low-confidence threshold."""


def register(agent: Agent[AgentDeps, str]) -> None:
    @agent.tool
    async def corpus_search(
        ctx: RunContext[AgentDeps],
        query: str = Field(
            description=(
                "Natural-language search query against the FAA Aeronautical "
                "Information Manual (AIM). Use for procedural questions, "
                "regulatory references, and definitions."
            )
        ),
        top_k: int = Field(
            default=DEFAULT_TOP_K,
            description="Number of chunks to return. Default 5. Max 10.",
            ge=1,
            le=10,
        ),
    ) -> CorpusSearchResult:
        """Semantic search over the FAA AIM corpus.

        Returns up to ``top_k`` chunks with similarity scores. When the
        result has ``low_confidence=True``, the agent should be cautious
        about quoting and may want to acknowledge uncertainty.
        """
        return await _execute(ctx.deps, query=query, top_k=top_k)


async def _execute(
    deps: AgentDeps,
    *,
    query: str,
    top_k: int,
) -> CorpusSearchResult:
    started = time.perf_counter()
    deps.trace.append_tool_call(tool_name=TOOL_NAME, args={"query": query, "top_k": top_k})

    if not query.strip():
        msg = "query must be a non-empty string"
        deps.trace.append_error(
            error_kind="tool_error:invalid_input", message=msg, tool_name=TOOL_NAME
        )
        raise ToolError(kind="invalid_input", retryable=False, user_message=msg)

    if deps.corpus_index is None:
        deps.trace.append_error(
            error_kind="tool_error:unavailable",
            message="corpus_index is not wired into AgentDeps.",
            tool_name=TOOL_NAME,
        )
        raise ToolError(
            kind="unavailable",
            retryable=False,
            user_message="The aviation corpus is not available in this environment.",
        )

    try:
        raw_hits = deps.corpus_index.search(query, top_k=top_k)
    except FileNotFoundError as exc:
        deps.trace.append_error(
            error_kind="tool_error:unavailable",
            message="corpus index not built",
            tool_name=TOOL_NAME,
        )
        raise ToolError(
            kind="unavailable",
            retryable=False,
            user_message="The aviation corpus index has not been built yet.",
        ) from exc

    confident_hits = search_passage_subset(raw_hits, min_score=LOW_CONFIDENCE_THRESHOLD)
    result = CorpusSearchResult(
        query=query,
        hits=[_to_wire(h) for h in raw_hits],
        low_confidence=len(confident_hits) == 0,
    )

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    if result.hits:
        preview = f"{len(result.hits)} hits; top: {result.hits[0].source}/{result.hits[0].section}"
    else:
        preview = "no hits"
    deps.trace.append_tool_result(
        tool_name=TOOL_NAME,
        result_preview=truncate_for_trace(preview),
        success=True,
        latency_ms=elapsed_ms,
    )
    return result


def _to_wire(hit: CorpusSearchHit) -> CorpusHit:
    return CorpusHit(
        chunk_id=hit.chunk_id,
        source=hit.source,
        section=hit.section,
        text=hit.text,
        score=hit.score,
    )
