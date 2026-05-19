"""Embedding providers.

Two implementations:

- :class:`SentenceTransformersEmbedder` — production, wraps
  ``sentence-transformers/BAAI/bge-small-en-v1.5`` (384-dim).
- :class:`FakeEmbedder` — deterministic CPU-only embedding for tests. Hashes
  whitespace tokens into a fixed-dim vector, normalizes to unit norm. Same
  input always produces the same vector.

The agent depends on the :class:`EmbeddingProvider` Protocol, so the index
and tools never know which implementation they're talking to.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Anything callable as ``embedder.embed(["text1", "text2"])`` -> list of vectors."""

    @property
    def dim(self) -> int: ...

    @property
    def model_name(self) -> str: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


# ----------------------------------------------------------------------
# Production embedder
# ----------------------------------------------------------------------


class SentenceTransformersEmbedder:
    """Sentence-transformers backed embedder.

    Loads the model lazily on first call so import time stays fast and tests
    that don't need real embeddings (the vast majority) never pay the cost.
    """

    DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
    DEFAULT_DIM = 384

    def __init__(self, model_name: str = DEFAULT_MODEL, device: str | None = None) -> None:
        self._model_name = model_name
        self._device = device
        self._model: object | None = None  # lazy import to keep cold start small

    @property
    def dim(self) -> int:
        return self.DEFAULT_DIM

    @property
    def model_name(self) -> str:
        return self._model_name

    def _load(self) -> object:
        if self._model is None:
            # Local import so tests that never call embed() don't load torch.
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name, device=self._device)
        return self._model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        encoded = model.encode(  # type: ignore[attr-defined]
            list(texts),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        # sentence-transformers returns numpy ndarray; convert to plain lists.
        return [list(map(float, row)) for row in encoded]


# ----------------------------------------------------------------------
# Deterministic fake embedder for tests
# ----------------------------------------------------------------------


class FakeEmbedder:
    """Hash-based deterministic embedder.

    Tokenizes text on whitespace and bins each token into one of ``dim``
    buckets via SHA1, accumulating a 1.0 per bucket. Normalizes to unit
    norm. The same string always produces the same vector; similar strings
    produce similar (but not identical) vectors, which is enough for unit
    tests that need a usable cosine-similarity signal without loading torch.
    """

    def __init__(self, dim: int = 64, model_name: str = "fake/hash-embedder") -> None:
        if dim <= 0:
            raise ValueError("dim must be positive.")
        self._dim = dim
        self._model_name = model_name

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        tokens = text.lower().split() or ["<empty>"]
        for token in tokens:
            # Non-security-critical hash for deterministic bucketing. blake2b is
            # FIPS-clean unlike md5/sha1; we use the first 4 bytes only.
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self._dim
            vec[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [v / norm for v in vec]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity between two (unit-norm) vectors. Used in tests."""
    if len(a) != len(b):
        raise ValueError(f"Vector dimension mismatch: {len(a)} vs {len(b)}.")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
