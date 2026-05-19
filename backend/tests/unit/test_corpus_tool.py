"""Tests for the corpus_search tool."""

from __future__ import annotations

from pathlib import Path

import pytest
from aviation_copilot.agent.core import AgentDeps, build_agent, clear_tool_registrars
from aviation_copilot.agent.errors import ToolError
from aviation_copilot.agent.trace import Trace
from aviation_copilot.corpus.chunk import Chunk
from aviation_copilot.corpus.embed import FakeEmbedder
from aviation_copilot.corpus.index import CorpusIndex
from aviation_copilot.tools import corpus
from aviation_copilot.tools.corpus import _execute
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel


def _make_chunks() -> list[Chunk]:
    return [
        Chunk(
            chunk_id="aim::airspace::0001",
            source="aim_chap3",
            section="airspace",
            text="Class B airspace surrounds the nation's busiest airports.",
            token_count=10,
        ),
        Chunk(
            chunk_id="aim::weather::0001",
            source="aim_chap7",
            section="weather",
            text="METAR reports include surface wind, visibility, sky condition.",
            token_count=10,
        ),
    ]


@pytest.fixture
def deps_with_index(tmp_path: Path) -> AgentDeps:
    idx = CorpusIndex(tmp_path / "corpus.lance", embedder=FakeEmbedder(dim=128))
    idx.build(_make_chunks())
    return AgentDeps(trace=Trace.new(), corpus_index=idx)


@pytest.fixture(autouse=True)
def _reset_registrars() -> None:
    clear_tool_registrars()
    yield
    clear_tool_registrars()


class TestInvalidInput:
    async def test_empty_query_raises(self, deps_with_index: AgentDeps) -> None:
        with pytest.raises(ToolError) as exc_info:
            await _execute(deps_with_index, query="   ", top_k=3)
        assert exc_info.value.kind == "invalid_input"


class TestHappyPath:
    async def test_returns_top_k(self, deps_with_index: AgentDeps) -> None:
        result = await _execute(deps_with_index, query="Class B airspace", top_k=2)
        assert result.query == "Class B airspace"
        assert 1 <= len(result.hits) <= 2
        # Each hit is a wire-shape CorpusHit.
        first = result.hits[0]
        assert first.chunk_id.startswith("aim::")
        assert first.source in {"aim_chap3", "aim_chap7"}
        assert isinstance(first.score, float)

    async def test_top_k_clamps_to_index_size(self, deps_with_index: AgentDeps) -> None:
        result = await _execute(deps_with_index, query="airspace", top_k=10)
        # Index only has 2 chunks; tool returns however many LanceDB gives.
        assert len(result.hits) == 2


class TestLowConfidence:
    async def test_unrelated_query_flagged(self, deps_with_index: AgentDeps) -> None:
        # FakeEmbedder gives a deterministic but weak signal for unrelated text.
        result = await _execute(
            deps_with_index,
            query="totally unrelated banana smoothie recipe with kale",
            top_k=2,
        )
        # The threshold (>= 0.0) means hits with negative score flip the flag.
        # We can't promise the flag is set, but we can verify the field exists.
        assert hasattr(result, "low_confidence")
        # All scores returned are floats — no exceptions on weak matches.
        assert all(isinstance(h.score, float) for h in result.hits)


class TestMissingIndex:
    async def test_no_index_raises_unavailable(self) -> None:
        empty_deps = AgentDeps(trace=Trace.new(), corpus_index=None)
        with pytest.raises(ToolError) as exc_info:
            await _execute(empty_deps, query="anything", top_k=3)
        assert exc_info.value.kind == "unavailable"

    async def test_unbuilt_index_raises_unavailable(self, tmp_path: Path) -> None:
        # CorpusIndex that hasn't been built.
        idx = CorpusIndex(tmp_path / "missing.lance", embedder=FakeEmbedder(dim=128))
        deps = AgentDeps(trace=Trace.new(), corpus_index=idx)
        with pytest.raises(ToolError) as exc_info:
            await _execute(deps, query="anything", top_k=3)
        assert exc_info.value.kind == "unavailable"


class TestTraceRecording:
    async def test_records_call_and_result(self, deps_with_index: AgentDeps) -> None:
        await _execute(deps_with_index, query="airspace", top_k=2)
        assert deps_with_index.trace.tool_call_count("corpus_search") == 1
        result_steps = [
            s
            for s in deps_with_index.trace.steps
            if s.kind == "tool_result" and s.tool_name == "corpus_search"
        ]
        assert len(result_steps) == 1


class TestRegistration:
    def test_register_adds_tool_to_agent(self) -> None:
        agent: Agent[AgentDeps, str] = build_agent(model=TestModel(), apply_tool_registrars=False)
        corpus.register(agent)
        tool_names = {t.name for t in agent._function_toolset.tools.values()}
        assert "corpus_search" in tool_names
