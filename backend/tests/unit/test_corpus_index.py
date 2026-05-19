"""Tests for the LanceDB-backed CorpusIndex.

Uses FakeEmbedder so tests don't load torch / a real model. Each test builds
its own index in a tmp dir for isolation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aviation_copilot.corpus.chunk import Chunk
from aviation_copilot.corpus.embed import FakeEmbedder
from aviation_copilot.corpus.index import CorpusIndex, search_passage_subset


def _make_chunks() -> list[Chunk]:
    return [
        Chunk(
            chunk_id="aim::airspace::0001",
            source="aim_chap3",
            section="airspace",
            text="Class B airspace surrounds the nation's busiest airports.",
            token_count=10,
            ordinal=0,
        ),
        Chunk(
            chunk_id="aim::weather::0001",
            source="aim_chap7",
            section="weather",
            text="METAR reports include surface wind, visibility, sky condition.",
            token_count=10,
            ordinal=0,
        ),
        Chunk(
            chunk_id="aim::comm::0001",
            source="aim_chap4",
            section="communications",
            text="ATIS broadcasts include current weather and active runway information.",
            token_count=10,
            ordinal=0,
        ),
    ]


@pytest.fixture
def index(tmp_path: Path) -> CorpusIndex:
    emb = FakeEmbedder(dim=128)
    idx = CorpusIndex(tmp_path / "corpus.lance", embedder=emb)
    count = idx.build(_make_chunks())
    assert count == 3
    return idx


class TestBuild:
    def test_empty_chunks_returns_zero(self, tmp_path: Path) -> None:
        idx = CorpusIndex(tmp_path / "empty.lance", embedder=FakeEmbedder(dim=64))
        assert idx.build([]) == 0

    def test_row_count_matches_input(self, index: CorpusIndex) -> None:
        assert index.row_count() == 3

    def test_sources_listed(self, index: CorpusIndex) -> None:
        srcs = index.sources()
        assert srcs == ["aim_chap3", "aim_chap4", "aim_chap7"]


class TestSearch:
    def test_query_returns_top_k(self, index: CorpusIndex) -> None:
        hits = index.search("Class B airspace", top_k=2)
        assert 0 < len(hits) <= 2
        # FakeEmbedder uses unit-norm vectors; cosine distance is in [0, 2],
        # so `1 - distance` (the score) is in [-1, 1] — relative ordering
        # matters, the sign does not.
        assert all(isinstance(h.score, float) for h in hits)

    def test_relevant_result_ranks_first(self, index: CorpusIndex) -> None:
        hits = index.search("class b airspace surrounds airports", top_k=3)
        assert hits[0].source == "aim_chap3"

    def test_weather_query_finds_metar(self, index: CorpusIndex) -> None:
        hits = index.search("METAR surface wind visibility", top_k=2)
        assert hits[0].source == "aim_chap7"

    def test_empty_query_returns_empty(self, index: CorpusIndex) -> None:
        assert index.search("") == []
        assert index.search("   ") == []

    def test_search_returns_typed_hits(self, index: CorpusIndex) -> None:
        hits = index.search("airspace", top_k=1)
        h = hits[0]
        assert h.chunk_id.startswith("aim::")
        assert h.text.startswith("Class B")
        assert h.section in ("airspace", "weather", "communications")


class TestReopen:
    def test_open_existing_index(self, tmp_path: Path) -> None:
        path = tmp_path / "reopen.lance"
        emb = FakeEmbedder(dim=64)
        idx1 = CorpusIndex(path, embedder=emb)
        idx1.build(_make_chunks())

        idx2 = CorpusIndex(path, embedder=emb)
        idx2.open()
        assert idx2.row_count() == 3
        hits = idx2.search("airspace", top_k=1)
        assert len(hits) == 1

    def test_missing_index_raises(self, tmp_path: Path) -> None:
        idx = CorpusIndex(tmp_path / "nope.lance", embedder=FakeEmbedder(dim=64))
        with pytest.raises(FileNotFoundError):
            idx.open()


class TestPassageSubsetFilter:
    def test_passes_through_when_threshold_low(self) -> None:
        from aviation_copilot.corpus.index import CorpusSearchHit

        hits = [
            CorpusSearchHit(chunk_id="a", source="s", section="x", text="t", score=0.5),
            CorpusSearchHit(chunk_id="b", source="s", section="x", text="t", score=0.2),
        ]
        assert len(search_passage_subset(hits, min_score=0.0)) == 2

    def test_filters_below_threshold(self) -> None:
        from aviation_copilot.corpus.index import CorpusSearchHit

        hits = [
            CorpusSearchHit(chunk_id="a", source="s", section="x", text="t", score=0.8),
            CorpusSearchHit(chunk_id="b", source="s", section="x", text="t", score=0.3),
            CorpusSearchHit(chunk_id="c", source="s", section="x", text="t", score=0.1),
        ]
        filtered = search_passage_subset(hits, min_score=0.5)
        assert len(filtered) == 1
        assert filtered[0].chunk_id == "a"
