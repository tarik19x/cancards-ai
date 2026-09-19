"""Retrieve relevant card chunks given a user question.

Three modes (settings.retrieval_mode; the default is the best measured):

- dense: Pinecone vector search only. What the live app served before point 1.
- hybrid: fuses that with a BM25 keyword search by Reciprocal Rank Fusion.
- hybrid_rerank: fuses 20 candidates from each, then Pinecone's hosted
  bge-reranker-v2-m3 reads the pool against the question and orders it.

Measured on the 100 held-out hard questions (95 answerable), recall@8, each method
run once (LLM/TODO.md point 1, tests/evals/recall_results.json):

    original chunks:   dense 0.321   hybrid 0.437   hybrid + rerank 0.637
    card-name chunks:  dense 0.826   hybrid 0.821   hybrid + rerank 0.958

The card-name chunks (namespace headers-v1) are worth about +0.40 and the reranker
+0.11 to +0.20. Keyword search on its own adds little once the card name is in. The
questions all name their card, so these numbers describe questions that do.

The hosted reranker is free for 500 requests a month, so it can run out. When a
rerank call fails the answer falls back to the hybrid order and reranking pauses for
ten minutes; a failing keyword index falls back to dense. Both are logged.
"""

import asyncio
import time
from typing import Literal

from langsmith import traceable
from pinecone.exceptions import PineconeException
from tenacity import RetryError

from app.clients.openai_client import embed_text
from app.clients.pinecone_client import query_vectors, rerank_documents
from app.config import get_settings
from app.logging_config import get_logger
from app.rag.bm25_index import bm25_search

log = get_logger(__name__)

# The constant from the original RRF paper (Cormack et al., 2009). Large
# enough that no single method's rank-1 result completely dominates the
# fused ranking just for being rank 1 in one list.
RRF_K = 60

# How deep each first-stage search goes before the reranker reads the pool.
# 20 per method fuses to about 34 unique candidates, and on the 95 practice
# questions that pool already contains 0.705 of the right paragraphs (the most
# any reranker could reach); 50 per method only lifts that to 0.811 while
# reading 83 candidates instead of 34.
RERANK_POOL = 20


def reciprocal_rank_fusion(*ranked_lists: list[dict], k: int = RRF_K) -> list[dict]:
    """Fuse ranked result lists into one list, ranked by combined RRF score.

    Each list contributes 1/(k + rank) per item it contains; an item found
    by multiple methods sums its contributions, so it outranks an item only
    one method liked as strongly.
    """
    scores: dict[str, float] = {}
    metadata_by_id: dict[str, dict] = {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked):
            scores[item["id"]] = scores.get(item["id"], 0.0) + 1.0 / (k + rank + 1)
            metadata_by_id.setdefault(item["id"], item["metadata"])

    fused_ids = sorted(scores, key=lambda i: scores[i], reverse=True)
    return [{"id": i, "score": scores[i], "metadata": metadata_by_id[i]} for i in fused_ids]


def rerank(query: str, candidates: list[dict]) -> list[dict]:
    """Reorder fused candidates by the hosted reranker's relevance score."""
    documents = [{"id": c["id"], "text": c["metadata"].get("text", "")} for c in candidates]
    ranked = rerank_documents(query, documents)
    return [{**candidates[r["index"]], "score": r["score"]} for r in ranked]


# After a failed rerank (most likely the monthly free allowance running out) skip the
# reranker for a while instead of making every request wait through the retries again.
RERANK_PAUSE_SECONDS = 600
_rerank_paused_until = 0.0

# Only errors that come from Pinecone or its retry wrapper fall back. Anything else
# (a bug, or the eval tooling's own spending stop) must surface, not be hidden.
_PINECONE_FAILURES = (PineconeException, RetryError)


def rerank_or_hybrid_order(query: str, candidates: list[dict]) -> list[dict]:
    global _rerank_paused_until
    if time.monotonic() < _rerank_paused_until:
        return candidates
    try:
        return rerank(query, candidates)
    except _PINECONE_FAILURES as exc:
        _rerank_paused_until = time.monotonic() + RERANK_PAUSE_SECONDS
        log.warning(
            "rerank_failed_using_hybrid_order",
            error=str(exc),
            paused_seconds=RERANK_PAUSE_SECONDS,
        )
        return candidates


@traceable(name="retrieve_chunks", run_type="retriever")
async def retrieve_chunks(
    query: str,
    top_k: int = 12,
    mode: Literal["dense", "hybrid", "hybrid_rerank"] | None = None,
) -> list[dict]:
    """Find the top_k most relevant chunks for query.

    mode=None uses settings.retrieval_mode. mode="dense" is Pinecone-only
    search, "hybrid" fuses dense + BM25 candidates via RRF, and "hybrid_rerank"
    fuses RERANK_POOL candidates from each, then has the reranker read them all
    against the query and keeps the best top_k. The rerank pool does not depend
    on top_k, so asking for 8 and for 50 cost the same single rerank request.
    The index section searched is settings.pinecone_namespace.
    """
    settings = get_settings()
    mode = mode or settings.retrieval_mode
    namespace = settings.pinecone_namespace or None
    embedding = await embed_text(query)
    pool = RERANK_POOL if mode == "hybrid_rerank" else top_k
    dense_matches = query_vectors(embedding=embedding, top_k=pool, namespace=namespace)

    if mode == "dense":
        matches = dense_matches
    else:
        try:
            # In a thread so the first keyword-index build, if it lands on a request,
            # does not freeze every other request while it downloads the corpus.
            keyword_matches = await asyncio.to_thread(bm25_search, query, top_k=pool)
        except PineconeException as exc:
            log.warning("keyword_index_unavailable_using_dense", error=str(exc))
            keyword_matches = []
        candidates = reciprocal_rank_fusion(dense_matches, keyword_matches)
        if mode == "hybrid":
            matches = candidates[:top_k]
        else:
            matches = rerank_or_hybrid_order(query, candidates)[:top_k]

    log.info("retrieved", query=query, count=len(matches), mode=mode)
    return matches
