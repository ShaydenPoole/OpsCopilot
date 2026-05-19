"""Tests for the embedding providers.

Only ``FakeEmbedder`` is exercised here; ``SentenceTransformersEmbedder``
loading torch + a real model is too heavy for unit tests and is covered by
the live verification path in data_pipeline/build_corpus_index.py.
"""

from __future__ import annotations

import math

import pytest
from aviation_copilot.corpus.embed import EmbeddingProvider, FakeEmbedder, cosine_similarity


class TestFakeEmbedderProperties:
    def test_dim_matches_constructor(self) -> None:
        emb = FakeEmbedder(dim=128)
        assert emb.dim == 128

    def test_invalid_dim_raises(self) -> None:
        with pytest.raises(ValueError):
            FakeEmbedder(dim=0)

    def test_model_name_default(self) -> None:
        assert FakeEmbedder().model_name == "fake/hash-embedder"

    def test_implements_protocol(self) -> None:
        emb = FakeEmbedder()
        assert isinstance(emb, EmbeddingProvider)


class TestFakeEmbedderOutput:
    def test_returns_correct_count(self) -> None:
        emb = FakeEmbedder(dim=32)
        vecs = emb.embed(["a", "b", "c"])
        assert len(vecs) == 3
        assert all(len(v) == 32 for v in vecs)

    def test_empty_input_returns_empty(self) -> None:
        assert FakeEmbedder().embed([]) == []

    def test_deterministic(self) -> None:
        emb1 = FakeEmbedder(dim=32)
        emb2 = FakeEmbedder(dim=32)
        v1 = emb1.embed(["hello world"])[0]
        v2 = emb2.embed(["hello world"])[0]
        assert v1 == v2

    def test_unit_norm(self) -> None:
        emb = FakeEmbedder(dim=64)
        vec = emb.embed(["the quick brown fox"])[0]
        norm = math.sqrt(sum(x * x for x in vec))
        assert math.isclose(norm, 1.0, abs_tol=1e-9)

    def test_different_inputs_produce_different_vectors(self) -> None:
        emb = FakeEmbedder(dim=128)
        a, b = emb.embed(["alpha beta gamma", "delta epsilon zeta"])
        assert a != b

    def test_similar_inputs_produce_similar_vectors(self) -> None:
        emb = FakeEmbedder(dim=512)
        v_long = emb.embed(["the FAA AIM defines class B airspace operating rules"])[0]
        v_close = emb.embed(["FAA AIM class B airspace rules"])[0]
        v_far = emb.embed(["banana smoothie recipe with kale"])[0]
        sim_close = cosine_similarity(v_long, v_close)
        sim_far = cosine_similarity(v_long, v_far)
        assert sim_close > sim_far

    def test_handles_empty_text(self) -> None:
        # Empty input still produces a deterministic vector (treated as "<empty>" sentinel).
        vecs = FakeEmbedder().embed([""])
        assert len(vecs) == 1
        assert len(vecs[0]) == 64

    def test_case_insensitive(self) -> None:
        emb = FakeEmbedder(dim=64)
        upper = emb.embed(["FAA AIM CHAPTER 4"])[0]
        lower = emb.embed(["faa aim chapter 4"])[0]
        assert upper == lower


class TestCosineSimilarity:
    def test_orthogonal_vectors(self) -> None:
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_identical_vectors(self) -> None:
        v = [1.0, 2.0, 3.0]
        assert math.isclose(cosine_similarity(v, v), 1.0)

    def test_dim_mismatch_raises(self) -> None:
        with pytest.raises(ValueError):
            cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])

    def test_zero_vector_returns_zero(self) -> None:
        assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0
