"""Tests for the recall harness's OpenAI/Pinecone cache -- fakes only, no API calls."""

import asyncio

import pytest

from scripts.llm_cache import BudgetExceeded
from scripts.recall_cache import POOL, RecallCache, corpus_tag


class Fakes:
    def __init__(self) -> None:
        self.embed_calls: list[str] = []
        self.query_calls: list[dict] = []

    async def embed(self, text: str) -> list[float]:
        self.embed_calls.append(text)
        return [float(len(text)), 1.0]

    def query(self, embedding, top_k, filter_dict=None, namespace=None) -> list[dict]:
        self.query_calls.append({"top_k": top_k, "filter": filter_dict})
        return [{"id": f"c::{i}", "score": 1 - i / 100, "metadata": {}} for i in range(top_k)]


def make(tmp_path, fakes, tag="tag1", **kwargs) -> RecallCache:
    return RecallCache(
        fakes.embed,
        fakes.query,
        tag=tag,
        embedding_model="m",
        embeddings_path=tmp_path / "e.json",
        queries_path=tmp_path / "q.json",
        **kwargs,
    )


def test_an_embedding_is_paid_for_once(tmp_path):
    fakes = Fakes()
    cache = make(tmp_path, fakes)
    first = asyncio.run(cache.embed_text("what is the fee?"))
    second = asyncio.run(cache.embed_text("what is the fee?"))
    assert first == second
    assert (cache.embeds_paid, cache.embeds_hit) == (1, 1)


def test_a_small_top_k_is_sliced_from_one_deep_query(tmp_path):
    fakes = Fakes()
    cache = make(tmp_path, fakes)
    deep = cache.query_vectors([1.0, 2.0], top_k=50)
    shallow = cache.query_vectors([1.0, 2.0], top_k=8)

    assert [m["id"] for m in shallow] == [m["id"] for m in deep[:8]]
    assert len(fakes.query_calls) == 1  # only the deep query was paid for
    assert fakes.query_calls[0]["top_k"] == POOL


def test_the_shallow_request_first_still_only_pays_once(tmp_path):
    fakes = Fakes()
    cache = make(tmp_path, fakes)
    cache.query_vectors([1.0, 2.0], top_k=8)
    cache.query_vectors([1.0, 2.0], top_k=50)
    assert len(fakes.query_calls) == 1
    assert fakes.query_calls[0]["top_k"] == POOL


def test_a_filtered_or_too_deep_query_is_passed_through_uncached(tmp_path):
    fakes = Fakes()
    cache = make(tmp_path, fakes)
    cache.query_vectors([1.0], top_k=8, filter_dict={"card_id": "x"})
    cache.query_vectors([1.0], top_k=8, filter_dict={"card_id": "x"})
    cache.query_vectors([1.0], top_k=POOL + 1)
    assert len(fakes.query_calls) == 3


def test_results_survive_a_new_process(tmp_path):
    fakes = Fakes()
    cache = make(tmp_path, fakes)
    asyncio.run(cache.embed_text("q"))
    cache.query_vectors([1.0], top_k=8)
    cache.flush()

    later_fakes = Fakes()
    later = make(tmp_path, later_fakes)
    asyncio.run(later.embed_text("q"))
    later.query_vectors([1.0], top_k=8)

    assert later_fakes.embed_calls == [] and later_fakes.query_calls == []


def test_a_changed_corpus_discards_saved_pinecone_results_but_keeps_embeddings(tmp_path):
    fakes = Fakes()
    cache = make(tmp_path, fakes, tag="old-corpus")
    asyncio.run(cache.embed_text("q"))
    cache.query_vectors([1.0], top_k=8)
    cache.flush()

    later_fakes = Fakes()
    later = make(tmp_path, later_fakes, tag="new-corpus")
    asyncio.run(later.embed_text("q"))
    later.query_vectors([1.0], top_k=8)

    assert later.queries_were_reset
    assert later_fakes.embed_calls == []  # embeddings depend only on the question
    assert len(later_fakes.query_calls) == 1  # results are re-fetched


def test_the_budget_stops_paid_calls_but_cached_ones_stay_free(tmp_path):
    fakes = Fakes()
    cache = make(tmp_path, fakes, max_paid_calls=1)
    asyncio.run(cache.embed_text("first"))
    asyncio.run(cache.embed_text("first"))  # cached, not counted against the cap
    with pytest.raises(BudgetExceeded):
        asyncio.run(cache.embed_text("second"))


def test_flush_runs_on_demand_so_a_crash_keeps_what_was_paid(tmp_path):
    fakes = Fakes()
    cache = make(tmp_path, fakes)
    asyncio.run(cache.embed_text("q"))
    assert not (tmp_path / "e.json").exists()  # under the save interval
    cache.flush()
    assert (tmp_path / "e.json").exists()


def test_corpus_tag_changes_when_the_corpus_file_changes(tmp_path):
    path = tmp_path / "corpus.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    first = corpus_tag(path)
    path.write_text('{"a": 2}', encoding="utf-8")
    assert corpus_tag(path) != first


class RerankFakes:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict]]] = []

    def rerank(self, query, documents):
        self.calls.append((query, documents))
        return [{"index": i, "score": 1.0 - i / 10} for i in range(len(documents))]


def make_reranker(tmp_path, rerank_fakes, **kwargs) -> RecallCache:
    fakes = Fakes()
    return RecallCache(
        fakes.embed,
        fakes.query,
        tag="t",
        embedding_model="m",
        embeddings_path=tmp_path / "e.json",
        queries_path=tmp_path / "q.json",
        rerank=rerank_fakes.rerank,
        rerank_model="rm",
        reranks_path=tmp_path / "r.json",
        **kwargs,
    )


DOCS = [{"id": "a", "text": "alpha"}, {"id": "b", "text": "beta"}]


def test_a_rerank_is_paid_for_once(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.recall_cache.time.sleep", lambda _s: None)
    rf = RerankFakes()
    cache = make_reranker(tmp_path, rf)
    first = cache.rerank_documents("q", DOCS)
    second = cache.rerank_documents("q", DOCS)
    assert first == second and len(rf.calls) == 1
    assert (cache.reranks_paid, cache.reranks_hit) == (1, 1)


def test_a_rerank_is_redone_when_a_candidates_text_changes(tmp_path, monkeypatch):
    # The card-name headers change the text under the same ids; a saved ranking
    # for the old text must not be reused.
    monkeypatch.setattr("scripts.recall_cache.time.sleep", lambda _s: None)
    rf = RerankFakes()
    cache = make_reranker(tmp_path, rf)
    cache.rerank_documents("q", DOCS)
    cache.rerank_documents("q", [{"id": "a", "text": "Card: X. alpha"}, DOCS[1]])
    assert len(rf.calls) == 2


def test_the_rerank_budget_stops_paid_requests_but_cached_ones_stay_free(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.recall_cache.time.sleep", lambda _s: None)
    cache = make_reranker(tmp_path, RerankFakes(), max_rerank_calls=1)
    cache.rerank_documents("q1", DOCS)
    cache.rerank_documents("q1", DOCS)  # cached, not counted
    with pytest.raises(BudgetExceeded):
        cache.rerank_documents("q2", DOCS)


def test_paid_reranks_are_spaced_out_to_stay_under_the_rate_limit(tmp_path, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("scripts.recall_cache.time.sleep", sleeps.append)
    cache = make_reranker(tmp_path, RerankFakes())
    cache.rerank_documents("q1", DOCS)
    cache.rerank_documents("q2", DOCS)
    assert sleeps and sleeps[-1] > 0  # the second request had to wait


def test_saved_reranks_survive_a_new_process(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.recall_cache.time.sleep", lambda _s: None)
    cache = make_reranker(tmp_path, RerankFakes())
    cache.rerank_documents("q", DOCS)
    cache.flush()

    later_fakes = RerankFakes()
    later = make_reranker(tmp_path, later_fakes)
    later.rerank_documents("q", DOCS)
    assert later_fakes.calls == [] and later.reranks_hit == 1
