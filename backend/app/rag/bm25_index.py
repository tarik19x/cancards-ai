"""In-memory BM25 keyword index over the same chunks Pinecone serves.

Built from Pinecone's own metadata rather than re-derived from cards.json or
the PDFs on disk, so there is exactly one source of truth for corpus content
and this works in production too -- the PDFs never ship in the Docker image
(see backend/scripts/fetch_documents.py), so re-deriving locally isn't an
option there.

The index is built once per process (a Pinecone read of the whole corpus)
and cached in memory for the life of the process -- point 13's single-worker
deployment means that happens exactly once per deploy, not once per request.

Reads the corpus via query(), not fetch() -- found while diagnosing a real
Pinecone egress-cap outage (September 2026, see LLM/TODO.md point 1): fetch()
always returns each vector's full float values (1536 dims, ~6KB each) with no
way to opt out, which Pinecone's own docs flag, recommending query() with
include_values=False for metadata-only reads instead. This corpus loader
never uses the vector values -- only the text metadata, to build BM25's
keyword index -- so fetch() was paying for and downloading ~6KB per chunk
that was thrown away immediately after every read.
"""

import json
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

from app.clients.pinecone_client import get_index
from app.config import get_settings
from app.logging_config import get_logger

log = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Pinecone serverless caps a single query's top_k at 10,000 -- comfortably
# above this project's ~8,400-chunk corpus, so one call reads everything.
MAX_TOP_K = 10_000


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class Bm25Corpus:
    bm25: BM25Okapi
    ids: list[str]
    metadatas: list[dict[str, Any]]


_corpus: Bm25Corpus | None = None
_disk_cache_path: Path | None = None
# The startup warm-up and an early request can both ask for the corpus; without this
# both would download it (about 11 MB of Pinecone data each) and build it twice.
_build_lock = threading.Lock()


def enable_disk_cache(path: Path) -> None:
    """Opt-in for dev scripts only; the server never calls this.

    Every script start otherwise re-reads the whole corpus from Pinecone, and
    dev and production share one free-tier egress quota -- repeated dev runs
    took the live site down once already. The cache is never invalidated
    automatically: after re-indexing (e.g. adding chunk headers), delete the
    file, or scripts will keep measuring the old text.
    """
    global _disk_cache_path
    _disk_cache_path = path


def _fetch_all_chunks() -> tuple[list[str], list[dict[str, Any]]]:
    if _disk_cache_path is not None and _disk_cache_path.exists():
        cached = json.loads(_disk_cache_path.read_text(encoding="utf-8"))
        log.info("bm25_corpus_from_disk_cache", fetched_at=cached["fetched_at"])
        return cached["ids"], cached["metadatas"]

    ids, metadatas = _fetch_all_chunks_from_pinecone()
    if _disk_cache_path is not None:
        _disk_cache_path.parent.mkdir(parents=True, exist_ok=True)
        # Written only after a complete read, via a temp file, so a failed or
        # interrupted fetch can't leave a truncated cache that later runs trust.
        tmp = _disk_cache_path.with_suffix(".tmp")
        payload = {
            "fetched_at": datetime.now(UTC).isoformat(),
            "ids": ids,
            "metadatas": metadatas,
        }
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(_disk_cache_path)
    return ids, metadatas


def _fetch_all_chunks_from_pinecone() -> tuple[list[str], list[dict[str, Any]]]:
    index = get_index()
    # The keyword index must be built from the same section of the index the vectors are
    # searched in, or it would score different text than the dense side sees.
    namespace = get_settings().pinecone_namespace or None
    stats = index.describe_index_stats()
    dimension = stats["dimension"]
    in_namespace = stats.get("namespaces", {}).get(namespace or "", {}).get("vector_count")
    total = in_namespace or stats["total_vector_count"]

    # A small non-zero constant, not a literal zero vector -- cosine
    # similarity is undefined for a zero-magnitude vector, and this query's
    # actual similarity ranking is irrelevant anyway: top_k covers the whole
    # corpus, so every vector comes back regardless of its score.
    dummy_vector = [1e-6] * dimension
    response = index.query(
        vector=dummy_vector,
        top_k=min(total, MAX_TOP_K) if total else MAX_TOP_K,
        include_values=False,
        include_metadata=True,
        namespace=namespace,
    )
    ids = [match["id"] for match in response["matches"]]
    metadatas = [
        dict(match["metadata"]) if match.get("metadata") else {} for match in response["matches"]
    ]
    return ids, metadatas


def set_corpus(ids: list[str], metadatas: list[dict[str, Any]]) -> None:
    """Install a corpus built elsewhere (dev scripts measuring a different
    version of the text, without a Pinecone read). The server never calls this.
    """
    global _corpus
    tokenized = [_tokenize(m.get("text", "")) for m in metadatas]
    _corpus = Bm25Corpus(bm25=BM25Okapi(tokenized), ids=ids, metadatas=metadatas)


def get_bm25_corpus() -> Bm25Corpus:
    """Build (once) and cache the BM25 index. The first call is slow -- it
    fetches the whole corpus from Pinecone; later calls reuse it.
    """
    global _corpus
    with _build_lock:
        if _corpus is None:
            ids, metadatas = _fetch_all_chunks()
            tokenized = [_tokenize(m.get("text", "")) for m in metadatas]
            bm25 = BM25Okapi(tokenized)
            _corpus = Bm25Corpus(bm25=bm25, ids=ids, metadatas=metadatas)
            log.info("bm25_index_built", chunk_count=len(ids))
        return _corpus


def bm25_search(query: str, top_k: int) -> list[dict[str, Any]]:
    """Keyword search. Returns the same shape as query_vectors: id, score, metadata."""
    corpus = get_bm25_corpus()
    if not corpus.ids:
        return []
    scores = corpus.bm25.get_scores(_tokenize(query))
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [
        {"id": corpus.ids[i], "score": float(scores[i]), "metadata": corpus.metadatas[i]}
        for i in ranked
    ]
