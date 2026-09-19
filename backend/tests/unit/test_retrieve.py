"""Unit tests for RRF fusion and hybrid/dense mode switching in retrieve.py.

No real Pinecone/OpenAI calls -- embed_text, query_vectors, and bm25_search
are all mocked.
"""

from unittest.mock import AsyncMock, patch

from app.rag.retrieve import reciprocal_rank_fusion, retrieve_chunks


def _match(chunk_id: str, score: float) -> dict:
    return {"id": chunk_id, "score": score, "metadata": {"text": chunk_id}}


def test_rrf_prefers_item_found_by_both_lists():
    dense = [_match("a", 0.9), _match("b", 0.8)]
    keyword = [_match("b", 5.0), _match("c", 4.0)]
    fused = reciprocal_rank_fusion(dense, keyword)
    assert fused[0]["id"] == "b"


def test_rrf_preserves_all_unique_ids():
    fused = reciprocal_rank_fusion([_match("a", 1)], [_match("b", 1)])
    assert {f["id"] for f in fused} == {"a", "b"}


def test_rrf_empty_lists():
    assert reciprocal_rank_fusion([], []) == []


def test_rrf_single_list_keeps_rank_order():
    ranked = [_match("x", 1), _match("y", 1)]
    fused = reciprocal_rank_fusion(ranked)
    assert [f["id"] for f in fused] == ["x", "y"]


async def test_retrieve_chunks_dense_mode_skips_bm25():
    with (
        patch("app.rag.retrieve.embed_text", new_callable=AsyncMock) as mock_embed,
        patch("app.rag.retrieve.query_vectors") as mock_query,
        patch("app.rag.retrieve.bm25_search") as mock_bm25,
    ):
        mock_embed.return_value = [0.1, 0.2]
        mock_query.return_value = [_match("a", 0.9)]

        result = await retrieve_chunks("question", top_k=5, mode="dense")

        assert result == [_match("a", 0.9)]
        mock_bm25.assert_not_called()


async def test_retrieve_chunks_hybrid_mode_fuses_both():
    with (
        patch("app.rag.retrieve.embed_text", new_callable=AsyncMock) as mock_embed,
        patch("app.rag.retrieve.query_vectors") as mock_query,
        patch("app.rag.retrieve.bm25_search") as mock_bm25,
    ):
        mock_embed.return_value = [0.1, 0.2]
        mock_query.return_value = [_match("a", 0.9)]
        mock_bm25.return_value = [_match("b", 3.0)]

        result = await retrieve_chunks("question", top_k=5, mode="hybrid")

        result_ids = {r["id"] for r in result}
        assert result_ids == {"a", "b"}
        mock_bm25.assert_called_once_with("question", top_k=5)


async def test_retrieve_chunks_defaults_to_dense():
    with (
        patch("app.rag.retrieve.embed_text", new_callable=AsyncMock) as mock_embed,
        patch("app.rag.retrieve.query_vectors") as mock_query,
        patch("app.rag.retrieve.bm25_search") as mock_bm25,
    ):
        mock_embed.return_value = [0.1, 0.2]
        mock_query.return_value = []

        await retrieve_chunks("question")

        mock_bm25.assert_not_called()
