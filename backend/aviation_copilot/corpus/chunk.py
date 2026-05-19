"""Text chunking for the aviation corpus.

v1 default is fixed 512-token windows with 64-token overlap, applied uniformly
to extracted HTML text. The plan's named revisit trigger is
``retrieval_recall_at_5 < 0.70`` in U7 — at which point switch to semantic
chunking by section headings (the ``semantic`` strategy below).

Token counting uses a simple whitespace tokenizer. The corpus's actual
embedding model uses its own tokenizer, but for chunking the goal is bounded
chunk size, not exact token-budget control — over- vs under-shoot of 10-20%
is acceptable.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

ChunkingStrategy = Literal["fixed", "semantic"]


@dataclass(frozen=True)
class Chunk:
    """A single retrievable chunk of corpus text.

    ``source`` and ``section`` are display-friendly identifiers carried through
    to the agent's citation text. ``chunk_id`` is stable across runs of the
    same chunking pass over the same source.
    """

    chunk_id: str
    source: str
    section: str
    text: str
    token_count: int
    # Optional: ordinal index within the source, for stable ordering.
    ordinal: int = 0
    # Free-form metadata the chunker wants to surface (page numbers, URLs, etc).
    extra: dict[str, str] = field(default_factory=dict)


# ----------------------------------------------------------------------
# Tokenization (whitespace; good enough for chunk-size bounding)
# ----------------------------------------------------------------------

_WS_SPLIT = re.compile(r"\s+")


def count_tokens(text: str) -> int:
    """Whitespace token count. ``""`` returns 0."""
    stripped = text.strip()
    if not stripped:
        return 0
    return len(_WS_SPLIT.split(stripped))


def tokenize(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    return _WS_SPLIT.split(stripped)


def detokenize(tokens: Iterable[str]) -> str:
    return " ".join(tokens)


# ----------------------------------------------------------------------
# Public chunking API
# ----------------------------------------------------------------------


def chunk_document(
    text: str,
    *,
    source: str,
    section: str = "body",
    strategy: ChunkingStrategy = "fixed",
    window_tokens: int = 512,
    overlap_tokens: int = 64,
) -> list[Chunk]:
    """Chunk ``text`` according to the selected strategy.

    Args:
        text: The full document body to chunk.
        source: Document identifier (e.g., "FAA-AIM-Chapter-4").
        section: Section name passed through to chunk citations.
        strategy: ``"fixed"`` (v1 default) or ``"semantic"`` (uses headings
            to split, fixed-window fallback for long sections).
        window_tokens: Target chunk size in tokens.
        overlap_tokens: Tokens of overlap between adjacent chunks. Must be
            strictly less than ``window_tokens``.

    Returns:
        A list of Chunk objects ordered by appearance in the source.
    """
    if window_tokens <= 0:
        raise ValueError("window_tokens must be positive.")
    if overlap_tokens < 0 or overlap_tokens >= window_tokens:
        raise ValueError("overlap_tokens must satisfy 0 <= overlap < window.")

    cleaned = _clean_whitespace(text)
    if not cleaned:
        return []

    if strategy == "fixed":
        return _chunk_fixed(
            cleaned,
            source=source,
            section=section,
            window=window_tokens,
            overlap=overlap_tokens,
        )
    if strategy == "semantic":
        return _chunk_semantic(
            cleaned,
            source=source,
            window=window_tokens,
            overlap=overlap_tokens,
        )
    raise ValueError(f"Unknown chunking strategy: {strategy!r}")


# ----------------------------------------------------------------------
# Strategy implementations
# ----------------------------------------------------------------------


_MULTI_WS = re.compile(r"\s+")
_HEADING_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+|[A-Z][A-Z\s,&/-]{5,}\.?\s*$)",
    flags=re.MULTILINE,
)


def _clean_whitespace(text: str) -> str:
    return _MULTI_WS.sub(" ", text).strip()


def _chunk_fixed(
    text: str,
    *,
    source: str,
    section: str,
    window: int,
    overlap: int,
) -> list[Chunk]:
    tokens = tokenize(text)
    if not tokens:
        return []
    step = window - overlap
    chunks: list[Chunk] = []
    ordinal = 0
    start = 0
    while start < len(tokens):
        end = min(start + window, len(tokens))
        body = detokenize(tokens[start:end])
        chunks.append(
            Chunk(
                chunk_id=f"{source}::{section}::{ordinal:04d}",
                source=source,
                section=section,
                text=body,
                token_count=end - start,
                ordinal=ordinal,
            )
        )
        ordinal += 1
        if end == len(tokens):
            break
        start += step
    return chunks


def _chunk_semantic(
    text: str,
    *,
    source: str,
    window: int,
    overlap: int,
) -> list[Chunk]:
    """Split by detected headings, then fixed-chunk any section that's too long."""
    sections = _split_by_headings(text)
    if not sections:
        return _chunk_fixed(text, source=source, section="body", window=window, overlap=overlap)

    chunks: list[Chunk] = []
    ordinal = 0
    for heading, body in sections:
        if count_tokens(body) <= window:
            chunks.append(
                Chunk(
                    chunk_id=f"{source}::{heading}::{ordinal:04d}",
                    source=source,
                    section=heading,
                    text=body,
                    token_count=count_tokens(body),
                    ordinal=ordinal,
                )
            )
            ordinal += 1
        else:
            for sub in _chunk_fixed(
                body, source=source, section=heading, window=window, overlap=overlap
            ):
                chunks.append(
                    Chunk(
                        chunk_id=f"{source}::{heading}::{ordinal:04d}",
                        source=sub.source,
                        section=sub.section,
                        text=sub.text,
                        token_count=sub.token_count,
                        ordinal=ordinal,
                        extra=sub.extra,
                    )
                )
                ordinal += 1
    return chunks


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    """Return a list of (heading, body) pairs detected via simple heuristic.

    The heuristic matches lines that look like numbered section headers
    (``"4.1.2 Approach Lighting"``) or ALL-CAPS titles. Real AIM HTML
    structure is more reliable; this is a fallback for text that's already
    been flattened.
    """
    lines = text.split(". ")
    sections: list[tuple[str, str]] = []
    current_heading = "introduction"
    current_body: list[str] = []
    for line in lines:
        if _HEADING_RE.match(line.strip()) and len(line.split()) <= 12:
            if current_body:
                sections.append((current_heading, ". ".join(current_body).strip()))
                current_body = []
            current_heading = line.strip().rstrip(".").lower().replace(" ", "-")[:80]
        else:
            current_body.append(line)
    if current_body:
        sections.append((current_heading, ". ".join(current_body).strip()))
    return [(h, b) for h, b in sections if b]
