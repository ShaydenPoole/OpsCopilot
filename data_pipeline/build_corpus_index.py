"""Build the LanceDB corpus index from downloaded FAA AIM HTML.

Pipeline:
    1. Read every HTML file under ``data/raw/faa_aim/``.
    2. Extract clean text via trafilatura.
    3. Chunk with fixed-window strategy (v1 default per the plan).
    4. Embed with BAAI/bge-small-en-v1.5 (or a configurable model).
    5. Write to a LanceDB index at ``data/corpus_index.lance/``.
    6. Emit ``data/corpus_version.json`` with corpus metadata + counts.

Optional ``--verify`` flag runs a small probe-query suite against the index
and reports per-query top-k hit counts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / "data" / "raw" / "faa_aim"
DEFAULT_OUT = ROOT / "data" / "corpus_index.lance"
DEFAULT_VERSION = ROOT / "data" / "corpus_version.json"
DEFAULT_PROBES = Path(__file__).resolve().parent / "probe_queries.jsonl"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build the FAA AIM corpus LanceDB index.")
    p.add_argument("--in", dest="in_dir", type=Path, default=DEFAULT_IN, help="HTML input dir.")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output LanceDB directory.")
    p.add_argument(
        "--version-file",
        type=Path,
        default=DEFAULT_VERSION,
        help="Path to write the corpus_version.json manifest.",
    )
    p.add_argument(
        "--model",
        type=str,
        default="BAAI/bge-small-en-v1.5",
        help="Embedding model name (must be a sentence-transformers model).",
    )
    p.add_argument(
        "--window",
        type=int,
        default=512,
        help="Chunk window size in tokens (v1 default: 512).",
    )
    p.add_argument(
        "--overlap",
        type=int,
        default=64,
        help="Chunk overlap in tokens (v1 default: 64).",
    )
    p.add_argument(
        "--strategy",
        type=str,
        choices=["fixed", "semantic"],
        default="fixed",
        help="Chunking strategy (plan default: fixed).",
    )
    p.add_argument(
        "--verify",
        action="store_true",
        help="Run probe queries after building.",
    )
    p.add_argument(
        "--probes",
        type=Path,
        default=DEFAULT_PROBES,
        help="JSONL file of probe queries for --verify.",
    )
    return p.parse_args()


def extract_html(path: Path) -> str:
    """Extract the body text from an HTML file via trafilatura."""
    import trafilatura  # type: ignore[import-not-found]

    html = path.read_text(encoding="utf-8", errors="replace")
    extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
    return extracted or ""


def build(
    in_dir: Path,
    out: Path,
    *,
    model_name: str,
    window: int,
    overlap: int,
    strategy: str,
) -> dict[str, object]:
    """Build the corpus index. Returns stats for the version manifest."""
    htmls = sorted(in_dir.glob("*.html"))
    if not htmls:
        raise SystemExit(f"No HTML files under {in_dir}. Run download_faa_aim.py first.")

    # Lazy-import to keep this file lightweight in dry runs.
    from aviation_copilot.corpus.chunk import chunk_document
    from aviation_copilot.corpus.embed import SentenceTransformersEmbedder
    from aviation_copilot.corpus.index import CorpusIndex

    all_chunks = []
    for html_path in htmls:
        source = html_path.stem  # e.g., "aim_chap4"
        text = extract_html(html_path)
        if not text.strip():
            print(f"[warn] {html_path.name}: no text extracted, skipping.", file=sys.stderr)
            continue
        chunks = chunk_document(
            text,
            source=source,
            strategy=strategy,
            window_tokens=window,
            overlap_tokens=overlap,
        )
        print(f"[chunk] {source}: {len(chunks)} chunks", file=sys.stderr)
        all_chunks.extend(chunks)

    if not all_chunks:
        raise SystemExit("No chunks produced. Check input HTML.")

    print(f"[embed] {len(all_chunks)} chunks via {model_name}...", file=sys.stderr)
    embedder = SentenceTransformersEmbedder(model_name=model_name)
    index = CorpusIndex(out, embedder=embedder)
    count = index.build(all_chunks, mode="overwrite")

    return {
        "chunk_count": count,
        "embedding_model": model_name,
        "embedding_dim": embedder.dim,
        "chunking_strategy": strategy,
        "window_tokens": window,
        "overlap_tokens": overlap,
        "source_files": [p.name for p in htmls],
        "built_at": datetime.now(timezone.utc).isoformat(),
    }


def write_version(version_file: Path, stats: dict[str, object]) -> None:
    version_file.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(stats, indent=2)
    version_file.write_text(payload + "\n")
    digest = hashlib.sha256(payload.encode()).hexdigest()[:12]
    print(f"[manifest] {version_file} (sha256[:12]={digest})", file=sys.stderr)


def verify_with_probes(out: Path, probes_path: Path, model_name: str) -> bool:
    if not probes_path.exists():
        print(f"[verify] No probes file at {probes_path}; skipping.", file=sys.stderr)
        return True
    from aviation_copilot.corpus.embed import SentenceTransformersEmbedder
    from aviation_copilot.corpus.index import CorpusIndex

    embedder = SentenceTransformersEmbedder(model_name=model_name)
    index = CorpusIndex(out, embedder=embedder)
    index.open()

    fail = 0
    for line in probes_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        probe = json.loads(line)
        query: str = probe["query"]
        expected_sources: list[str] = probe.get("expected_any_source", [])
        hits = index.search(query, top_k=5)
        hit_sources = [h.source for h in hits]
        ok = (not expected_sources) or any(s in hit_sources for s in expected_sources)
        status = "ok " if ok else "MISS"
        print(
            f"[probe] {status} '{query[:60]}' -> {hit_sources[:3]}",
            file=sys.stderr,
        )
        if not ok:
            fail += 1
    if fail:
        print(f"\n{fail} probes missed expected sources.", file=sys.stderr)
        return False
    return True


def main() -> int:
    args = parse_args()
    stats = build(
        args.in_dir,
        args.out,
        model_name=args.model,
        window=args.window,
        overlap=args.overlap,
        strategy=args.strategy,
    )
    write_version(args.version_file, stats)
    print(
        f"\nBuilt {args.out} with {stats['chunk_count']} chunks "
        f"({stats['embedding_dim']}-dim {stats['embedding_model']}).",
        file=sys.stderr,
    )
    if args.verify and not verify_with_probes(args.out, args.probes, args.model):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
