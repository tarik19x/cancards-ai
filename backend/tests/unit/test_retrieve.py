"""Unit tests for RRF fusion and the retrieval modes in retrieve.py.

No real Pinecone/OpenAI calls -- embed_text, query_vectors, bm25_search,
rerank_documents and the settings are all stubbed.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pinecone.exceptions import PineconeApiException
from tenacity import RetryError

from app.rag import retrieve
from app.rag.retrieve import (
    RERANK_PAUSE_SECONDS,
    RERANK_POOL,
    reciprocal_rank_fusion,
    retrieve_chunks,
)


def _match(chunk_id: str, score: float) -> dict:
    return {"id": chunk_id, "score": score, "metadata": {"text": chunk_id}}


@pytest.fixture
def settings(monkeypatch):
    """Dense search on the default namespace unless a test says otherwise."""
    stub = SimpleNamespace(retrieval_mode="dense", pinecone_namespace="")
    monkeypatch.setattr("app.rag.retrieve.get_settings", lambda: stub)
    monkeypatch.setattr(retrieve, "_rerank_paused_until", 0.0)
    return stub


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


async def test_retrieve_chunks_dense_mode_skips_bm25(settings):
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


async def test_retrieve_chunks_hybrid_mode_fuses_both(settings):
    with (
        patch("app.rag.retrieve.embed_text", new_callable=AsyncMock) as mock_embed,
        patch("app.rag.retrieve.query_vectors") as mock_query,
        patch("app.rag.retrieve.bm25_search") as mock_bm25,
    ):
        mock_embed.return_value = [0.1, 0.2]
        mock_query.return_value = [_match("a", 0.9)]
        mock_bm25.return_value = [_match("b", 3.0)]

        result = await retrieve_chunks("question", top_k=5, mode="hybrid")

        assert {r["id"] for r in result} == {"a", "b"}
        mock_bm25.assert_called_once_with("question", top_k=5)


async def test_the_mode_comes_from_settings_when_not_given(settings):
    settings.retrieval_mode = "hybrid"
    with (
        patch("app.rag.retrieve.embed_text", new_callable=AsyncMock) as mock_embed,
        patch("app.rag.retrieve.query_vectors") as mock_query,
        patch("app.rag.retrieve.bm25_search") as mock_bm25,
    ):
        mock_embed.return_value = [0.1]
        mock_query.return_value = [_match("a", 0.9)]
        mock_bm25.return_value = [_match("b", 3.0)]

        await retrieve_chunks("question")

        mock_bm25.assert_called_once()


async def test_an_explicit_mode_overrides_settings(settings):
    settings.retrieval_mode = "hybrid_rerank"
    with (
        patch("app.rag.retrieve.embed_text", new_callable=AsyncMock) as mock_embed,
        patch("app.rag.retrieve.query_vectors") as mock_query,
        patch("app.rag.retrieve.bm25_search") as mock_bm25,
        patch("app.rag.retrieve.rerank_documents") as mock_rerank,
    ):
        mock_embed.return_value = [0.1]
        mock_query.return_value = [_match("a", 0.9)]

        await retrieve_chunks("question", mode="dense")

        mock_bm25.assert_not_called()
        mock_rerank.assert_not_called()


async def test_the_configured_namespace_is_searched_and_empty_means_the_default(settings):
    with (
        patch("app.rag.retrieve.embed_text", new_callable=AsyncMock) as mock_embed,
        patch("app.rag.retrieve.query_vectors") as mock_query,
    ):
        mock_embed.return_value = [0.1]
        mock_query.return_value = []

        settings.pinecone_namespace = "headers-v1"
        await retrieve_chunks("question", top_k=3, mode="dense")
        assert mock_query.call_args.kwargs["namespace"] == "headers-v1"

        settings.pinecone_namespace = ""
        await retrieve_chunks("question", top_k=3, mode="dense")
        assert mock_query.call_args.kwargs["namespace"] is None


async def test_hybrid_rerank_reads_a_fixed_pool_and_returns_the_rerankers_order(settings):
    with (
        patch("app.rag.retrieve.embed_text", new_callable=AsyncMock) as mock_embed,
        patch("app.rag.retrieve.query_vectors") as mock_query,
        patch("app.rag.retrieve.bm25_search") as mock_bm25,
        patch("app.rag.retrieve.rerank_documents") as mock_rerank,
    ):
        mock_embed.return_value = [0.1, 0.2]
        mock_query.return_value = [_match("a", 0.9), _match("b", 0.8)]
        mock_bm25.return_value = [_match("c", 3.0)]
        # The reranker says the third candidate is best, then the first.
        mock_rerank.return_value = [{"index": 2, "score": 0.9}, {"index": 0, "score": 0.5}]

        result = await retrieve_chunks("question", top_k=1, mode="hybrid_rerank")

        assert len(result) == 1 and result[0]["score"] == 0.9
        # Pool depth is fixed and does not follow top_k.
        assert mock_query.call_args.kwargs["top_k"] == RERANK_POOL
        mock_bm25.assert_called_once_with("question", top_k=RERANK_POOL)
        documents = mock_rerank.call_args.args[1]
        assert {d["id"] for d in documents} == {"a", "b", "c"}
        assert all(d["text"] for d in documents)


async def test_hybrid_rerank_pool_is_the_same_for_top_k_8_and_50(settings):
    with (
        patch("app.rag.retrieve.embed_text", new_callable=AsyncMock) as mock_embed,
        patch("app.rag.retrieve.query_vectors") as mock_query,
        patch("app.rag.retrieve.bm25_search") as mock_bm25,
        patch("app.rag.retrieve.rerank_documents") as mock_rerank,
    ):
        mock_embed.return_value = [0.1]
        mock_query.return_value = [_match("a", 0.9)]
        mock_bm25.return_value = []
        mock_rerank.return_value = [{"index": 0, "score": 1.0}]

        await retrieve_chunks("question", top_k=8, mode="hybrid_rerank")
        await retrieve_chunks("question", top_k=50, mode="hybrid_rerank")

        depths = [call.kwargs["top_k"] for call in mock_query.call_args_list]
        assert depths == [RERANK_POOL, RERANK_POOL]


def _pinecone_failure() -> PineconeApiException:
    return PineconeApiException(status=429, reason="egress or rerank limit")


async def test_a_failed_rerank_falls_back_to_the_hybrid_order_and_pauses_reranking(settings):
    with (
        patch("app.rag.retrieve.embed_text", new_callable=AsyncMock) as mock_embed,
        patch("app.rag.retrieve.query_vectors") as mock_query,
        patch("app.rag.retrieve.bm25_search") as mock_bm25,
        patch("app.rag.retrieve.rerank_documents") as mock_rerank,
    ):
        mock_embed.return_value = [0.1]
        mock_query.return_value = [_match("a", 0.9), _match("b", 0.8)]
        mock_bm25.return_value = [_match("c", 3.0)]
        mock_rerank.side_effect = _pinecone_failure()
        hybrid_order = [
            m["id"] for m in reciprocal_rank_fusion(mock_query.return_value, mock_bm25.return_value)
        ]

        first = await retrieve_chunks("question", top_k=3, mode="hybrid_rerank")
        second = await retrieve_chunks("question", top_k=3, mode="hybrid_rerank")

        assert [m["id"] for m in first] == hybrid_order  # answered, not an error
        assert [m["id"] for m in second] == hybrid_order
        assert mock_rerank.call_count == 1  # the second question did not retry the reranker


async def test_reranking_resumes_after_the_pause(settings, monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr("app.rag.retrieve.time.monotonic", lambda: clock["now"])
    with (
        patch("app.rag.retrieve.embed_text", new_callable=AsyncMock) as mock_embed,
        patch("app.rag.retrieve.query_vectors") as mock_query,
        patch("app.rag.retrieve.bm25_search") as mock_bm25,
        patch("app.rag.retrieve.rerank_documents") as mock_rerank,
    ):
        mock_embed.return_value = [0.1]
        mock_query.return_value = [_match("a", 0.9)]
        mock_bm25.return_value = []
        mock_rerank.side_effect = [RetryError(last_attempt=None), [{"index": 0, "score": 1.0}]]

        await retrieve_chunks("q", mode="hybrid_rerank")  # fails, pauses
        clock["now"] += RERANK_PAUSE_SECONDS - 1
        await retrieve_chunks("q", mode="hybrid_rerank")  # still paused
        assert mock_rerank.call_count == 1
        clock["now"] += 2
        await retrieve_chunks("q", mode="hybrid_rerank")  # paused window is over
        assert mock_rerank.call_count == 2


async def test_an_error_that_is_not_from_pinecone_is_not_swallowed(settings):
    # The eval tooling's own spending stop, or a real bug, must surface rather than
    # quietly turn a measured "rerank" run into a hybrid one.
    with (
        patch("app.rag.retrieve.embed_text", new_callable=AsyncMock) as mock_embed,
        patch("app.rag.retrieve.query_vectors") as mock_query,
        patch("app.rag.retrieve.bm25_search") as mock_bm25,
        patch("app.rag.retrieve.rerank_documents") as mock_rerank,
    ):
        mock_embed.return_value = [0.1]
        mock_query.return_value = [_match("a", 0.9)]
        mock_bm25.return_value = []
        mock_rerank.side_effect = RuntimeError("a bug")

        with pytest.raises(RuntimeError):
            await retrieve_chunks("question", mode="hybrid_rerank")


async def test_a_failing_keyword_index_falls_back_to_dense_results(settings):
    with (
        patch("app.rag.retrieve.embed_text", new_callable=AsyncMock) as mock_embed,
        patch("app.rag.retrieve.query_vectors") as mock_query,
        patch("app.rag.retrieve.bm25_search") as mock_bm25,
    ):
        mock_embed.return_value = [0.1]
        mock_query.return_value = [_match("a", 0.9), _match("b", 0.8)]
        mock_bm25.side_effect = _pinecone_failure()

        result = await retrieve_chunks("question", top_k=5, mode="hybrid")

        assert [m["id"] for m in result] == ["a", "b"]
