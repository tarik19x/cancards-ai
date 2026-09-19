"""Retrieve relevant card chunks given a user question.

Hybrid mode fuses Pinecone's dense vector search with a BM25 keyword search
over the same corpus using Reciprocal Rank Fusion, so an exact term a card's
own agreement uses (a product name, a specific clause) can surface a chunk
that's a weak semantic match. Measured on the point-1 eval set (see
tests/evals/recall_results.json), hybrid alone actually scores slightly
*below* dense-only on recall@8 (0.9694 vs 0.9861) -- RRF just merges two
rankings without re-scoring, and this 8,426-chunk corpus has enough
near-duplicate legal boilerplate across cards that BM25 sometimes pulls in
a competing chunk ahead of the one wanted. Reranking (point 1h) re-scores
the fused pool and is expected to recover this. Dense stays the default
until that's measured and the full pipeline is shown to actually be better
-- an unproven regression has no business being what the live app serves.
"""

from typing import Literal

from langsmith import traceable

from app.clients.openai_client import embed_text
from app.clients.pinecone_client import query_vectors
from app.logging_config import get_logger
from app.rag.bm25_index import bm25_search

log = get_logger(__name__)

# The constant from the original RRF paper (Cormack et al., 2009). Large
# enough that no single method's rank-1 result completely dominates the
# fused ranking just for being rank 1 in one list.
RRF_K = 60


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


@traceable(name="retrieve_chunks", run_type="retriever")
async def retrieve_chunks(
    query: str, top_k: int = 12, mode: Literal["dense", "hybrid"] = "dense"
) -> list[dict]:
    """Find the top_k most relevant chunks for query.

    mode="dense" (default) is Pinecone-only search -- what's actually served
    today, see the module docstring for why.
    mode="hybrid" fuses dense + BM25 candidates via RRF.
    """
    embedding = await embed_text(query)
    dense_matches = query_vectors(embedding=embedding, top_k=top_k)

    if mode == "dense":
        matches = dense_matches
    else:
        keyword_matches = bm25_search(query, top_k=top_k)
        matches = reciprocal_rank_fusion(dense_matches, keyword_matches)[:top_k]

    log.info("retrieved", query=query, count=len(matches), mode=mode)
    return matches
