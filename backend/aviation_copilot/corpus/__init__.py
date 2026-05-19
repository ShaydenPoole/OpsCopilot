"""Aviation document corpus — FAA AIM ingestion, chunking, embedding, retrieval.

- :mod:`chunk`  : Fixed-window chunker with semantic-by-headings fallback.
- :mod:`embed`  : Local sentence-transformers wrapper with deterministic fake mode.
- :mod:`index`  : LanceDB index management — build, append, search.
"""

from aviation_copilot.corpus.chunk import Chunk, ChunkingStrategy, chunk_document
from aviation_copilot.corpus.embed import (
    EmbeddingProvider,
    FakeEmbedder,
    SentenceTransformersEmbedder,
)
from aviation_copilot.corpus.index import CorpusIndex, CorpusSearchHit

__all__ = [
    "Chunk",
    "ChunkingStrategy",
    "CorpusIndex",
    "CorpusSearchHit",
    "EmbeddingProvider",
    "FakeEmbedder",
    "SentenceTransformersEmbedder",
    "chunk_document",
]
