"""LanceDB-backed corpus index.

Schema: ``(chunk_id, source, section, text, ordinal, embedding)``. The
embedding column dimension is fixed at index-build time; queries embed the
query string with the same provider.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aviation_copilot.corpus.chunk import Chunk
from aviation_copilot.corpus.embed import EmbeddingProvider

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class CorpusSearchHit:
    """One result row from a corpus search."""

    chunk_id: str
    source: str
    section: str
    text: str
    score: float
    ordinal: int = 0


class CorpusIndex:
    """LanceDB collection of chunked + embedded aviation corpus text.

    Treats LanceDB as a typed Python collection: ``build`` populates from
    chunks + an embedder, ``search`` returns top-K hits ordered by score.
    """

    TABLE_NAME = "aviation_corpus"

    def __init__(self, db_path: str | Path, embedder: EmbeddingProvider) -> None:
        self._db_path = Path(db_path)
        self._embedder = embedder
        self._db: Any | None = None
        self._table: Any | None = None

    # ------------------------------------------------------------------
    # Build / open
    # ------------------------------------------------------------------

    def build(self, chunks: Iterable[Chunk], *, mode: str = "overwrite") -> int:
        """Embed every chunk and write to LanceDB. Returns the chunk count."""
        chunks_list = list(chunks)
        if not chunks_list:
            return 0
        vectors = self._embedder.embed([c.text for c in chunks_list])
        rows = [
            {
                "chunk_id": c.chunk_id,
                "source": c.source,
                "section": c.section,
                "text": c.text,
                "ordinal": c.ordinal,
                "embedding": vec,
            }
            for c, vec in zip(chunks_list, vectors, strict=True)
        ]

        import lancedb

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(self._db_path))
        self._table = self._db.create_table(self.TABLE_NAME, data=rows, mode=mode)
        return len(rows)

    def open(self) -> None:
        """Open an existing index for read-only search."""
        import lancedb

        if not self._db_path.exists():
            raise FileNotFoundError(
                f"Corpus index not found at {self._db_path}. "
                "Run data_pipeline/build_corpus_index.py to create it."
            )
        self._db = lancedb.connect(str(self._db_path))
        self._table = self._db.open_table(self.TABLE_NAME)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, *, top_k: int = 5) -> list[CorpusSearchHit]:
        """Return the top-``top_k`` chunks by cosine similarity to ``query``."""
        if self._table is None:
            self.open()
        if not query.strip():
            return []
        query_vec = self._embedder.embed([query])[0]
        results = (
            self._table.search(query_vec)  # type: ignore[union-attr]
            .limit(top_k)
            .to_list()
        )
        return [
            CorpusSearchHit(
                chunk_id=r["chunk_id"],
                source=r["source"],
                section=r["section"],
                text=r["text"],
                ordinal=int(r.get("ordinal", 0)),
                # LanceDB returns _distance; convert to similarity for clarity.
                score=float(1.0 - r.get("_distance", 0.0)),
            )
            for r in results
        ]

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def row_count(self) -> int:
        if self._table is None:
            self.open()
        return int(self._table.count_rows())  # type: ignore[union-attr]

    def sources(self) -> list[str]:
        if self._table is None:
            self.open()
        # Pull just the source column via arrow; avoids pandas dependency.
        arrow_table = self._table.to_arrow().select(["source"])  # type: ignore[union-attr]
        return sorted(set(arrow_table.column("source").to_pylist()))


# ----------------------------------------------------------------------
# Public helpers
# ----------------------------------------------------------------------


def search_passage_subset(
    hits: Sequence[CorpusSearchHit],
    *,
    min_score: float = 0.0,
) -> list[CorpusSearchHit]:
    """Filter hits to those scoring at least ``min_score``.

    The agent uses this to decide whether to trust the retrieval ("low
    confidence" if no hit clears the threshold) — see the corpus_search
    tool implementation in U5.
    """
    return [h for h in hits if h.score >= min_score]
