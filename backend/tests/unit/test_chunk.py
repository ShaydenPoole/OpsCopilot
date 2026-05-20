"""Tests for the corpus chunking strategy."""

from __future__ import annotations

import dataclasses

import pytest
from aviation_copilot.corpus.chunk import (
    Chunk,
    chunk_document,
    count_tokens,
    detokenize,
    tokenize,
)


class TestTokenization:
    def test_count_tokens_simple(self) -> None:
        assert count_tokens("one two three") == 3

    def test_count_tokens_empty(self) -> None:
        assert count_tokens("") == 0
        assert count_tokens("   ") == 0

    def test_count_tokens_multispace(self) -> None:
        assert count_tokens("a    b\n\nc\td") == 4

    def test_round_trip(self) -> None:
        text = "hello world  foo"
        assert detokenize(tokenize(text)) == "hello world foo"


class TestFixedChunking:
    def test_short_text_one_chunk(self) -> None:
        chunks = chunk_document(
            "short body text under window size",
            source="src1",
            window_tokens=512,
            overlap_tokens=64,
        )
        assert len(chunks) == 1
        assert chunks[0].source == "src1"
        assert chunks[0].section == "body"
        assert chunks[0].ordinal == 0

    def test_long_text_multiple_chunks(self) -> None:
        tokens = " ".join(f"tok{i}" for i in range(1500))
        chunks = chunk_document(tokens, source="src", window_tokens=512, overlap_tokens=64)
        # With 512 window and 64 overlap, step = 448. 1500 / 448 ~ 3.35 -> 4 chunks.
        assert len(chunks) == 4
        # First chunk has 512 tokens; ordinals are sequential.
        assert chunks[0].token_count == 512
        for i, c in enumerate(chunks):
            assert c.ordinal == i
            assert c.chunk_id == f"src::body::{i:04d}"

    def test_overlap_preserves_continuity(self) -> None:
        tokens = " ".join(f"tok{i}" for i in range(800))
        chunks = chunk_document(tokens, source="src", window_tokens=500, overlap_tokens=100)
        # window=500, overlap=100, step=400.
        # chunk[0] = tokens 0..499; chunk[1] = tokens 400..899.
        # The 100-token overlap region is tokens 400..499 — it's the LAST 100
        # of chunk 0 and the FIRST 100 of chunk 1.
        first_chunk_tail = chunks[0].text.split()[-100:]
        second_chunk_head = chunks[1].text.split()[:100]
        assert first_chunk_tail == second_chunk_head

    def test_empty_text_zero_chunks(self) -> None:
        assert chunk_document("", source="src") == []
        assert chunk_document("   ", source="src") == []

    def test_invalid_window_raises(self) -> None:
        with pytest.raises(ValueError):
            chunk_document("x", source="s", window_tokens=0)

    def test_overlap_too_large_raises(self) -> None:
        with pytest.raises(ValueError):
            chunk_document("x y z", source="s", window_tokens=10, overlap_tokens=10)
        with pytest.raises(ValueError):
            chunk_document("x y z", source="s", window_tokens=10, overlap_tokens=11)


class TestSemanticChunking:
    def test_falls_back_to_fixed_when_no_headings(self) -> None:
        text = " ".join(f"tok{i}" for i in range(1000))
        chunks = chunk_document(
            text,
            source="src",
            strategy="semantic",
            window_tokens=400,
            overlap_tokens=50,
        )
        assert len(chunks) >= 2
        # Falls back means it stays inside the window budget.
        for c in chunks:
            assert c.token_count <= 400

    def test_splits_short_sections_into_own_chunks(self) -> None:
        # Use a numbered-header pattern the heuristic recognizes.
        text = (
            "4.1.2 Approach Lighting. "
            "Approach lighting helps pilots transition from instrument to visual flight. "
            "4.1.3 Visual Approach Slope Indicator. "
            "VASI provides visual descent guidance information."
        )
        chunks = chunk_document(
            text,
            source="aim",
            strategy="semantic",
            window_tokens=512,
            overlap_tokens=0,
        )
        # We should get at least 2 chunks split by the numbered headings.
        assert len(chunks) >= 2
        sections = {c.section for c in chunks}
        # Numbered headings get lowercased and hyphenated.
        assert any("approach" in s for s in sections)


class TestChunkObject:
    def test_chunk_id_stable_across_runs(self) -> None:
        text = " ".join(f"tok{i}" for i in range(900))
        a = chunk_document(text, source="src")
        b = chunk_document(text, source="src")
        ids_a = [c.chunk_id for c in a]
        ids_b = [c.chunk_id for c in b]
        assert ids_a == ids_b

    def test_chunk_is_immutable(self) -> None:
        c = Chunk(chunk_id="a", source="s", section="x", text="t", token_count=1)
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.text = "other"  # type: ignore[misc]
