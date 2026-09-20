"""Unit tests for the in-memory BM25 index -- no real Pinecone calls.

The module-level cache (_corpus) is monkeypatched directly with a small
synthetic corpus, bypassing get_bm25_corpus()'s Pinecone fetch.
"""

import pytest
from rank_bm25 import BM25Okapi

from app.rag import bm25_index
from app.rag.bm25_index import Bm25Corpus, _fetch_all_chunks, _tokenize, bm25_search


def test_tokenize_lowercases_and_splits_on_punctuation():
    assert _tokenize("Annual Fee: $150 CAD!") == ["annual", "fee", "150", "cad"]


class FakeIndex:
    """Stands in for the Pinecone index -- records what query() was called
    with, so a test can assert on the include_values/top_k choice, not just
    the returned data.
    """

    def __init__(
        self,
        dimension: int,
        total_vector_count: int,
        matches: list[dict],
        namespaces: dict | None = None,
    ):
        self._stats = {"dimension": dimension, "total_vector_count": total_vector_count}
        if namespaces is not None:
            self._stats["namespaces"] = namespaces
        self._matches = matches
        self.query_calls: list[dict] = []

    def describe_index_stats(self) -> dict:
        return self._stats

    def query(self, **kwargs) -> dict:
        self.query_calls.append(kwargs)
        return {"matches": self._matches}


def test_fetch_all_chunks_reads_metadata_without_vector_values(monkeypatch):
    fake_matches = [
        {"id": "amex-cobalt::fees", "metadata": {"text": "The fee is $0."}},
        {"id": "rbc-avion-vi::rewards", "metadata": {"text": "Earns points."}},
    ]
    fake_index = FakeIndex(dimension=1536, total_vector_count=2, matches=fake_matches)
    monkeypatch.setattr(bm25_index, "get_index", lambda: fake_index)

    ids, metadatas = _fetch_all_chunks()

    assert ids == ["amex-cobalt::fees", "rbc-avion-vi::rewards"]
    assert metadatas == [{"text": "The fee is $0."}, {"text": "Earns points."}]
    # The whole point of this rewrite: never pay for vector values we throw
    # away immediately -- Pinecone's fetch() can't skip them, query() can.
    assert fake_index.query_calls[0]["include_values"] is False
    assert fake_index.query_calls[0]["include_metadata"] is True


def test_fetch_all_chunks_requests_top_k_covering_the_whole_corpus(monkeypatch):
    fake_index = FakeIndex(dimension=1536, total_vector_count=8426, matches=[])
    monkeypatch.setattr(bm25_index, "get_index", lambda: fake_index)

    _fetch_all_chunks()

    assert fake_index.query_calls[0]["top_k"] == 8426


def test_fetch_all_chunks_caps_top_k_at_pinecones_10k_query_limit(monkeypatch):
    fake_index = FakeIndex(dimension=1536, total_vector_count=50_000, matches=[])
    monkeypatch.setattr(bm25_index, "get_index", lambda: fake_index)

    _fetch_all_chunks()

    assert fake_index.query_calls[0]["top_k"] == 10_000


def test_fetch_all_chunks_handles_a_match_with_no_metadata(monkeypatch):
    fake_index = FakeIndex(
        dimension=1536, total_vector_count=1, matches=[{"id": "some-id", "metadata": None}]
    )
    monkeypatch.setattr(bm25_index, "get_index", lambda: fake_index)

    ids, metadatas = _fetch_all_chunks()

    assert ids == ["some-id"]
    assert metadatas == [{}]


def test_disk_cache_reads_pinecone_once_then_serves_from_disk(monkeypatch, tmp_path):
    fake_index = FakeIndex(
        dimension=1536,
        total_vector_count=1,
        matches=[{"id": "a::fees", "metadata": {"text": "The fee is $0."}}],
    )
    monkeypatch.setattr(bm25_index, "get_index", lambda: fake_index)
    monkeypatch.setattr(bm25_index, "_disk_cache_path", tmp_path / "corpus.json")

    first = _fetch_all_chunks()
    second = _fetch_all_chunks()

    assert first == second == (["a::fees"], [{"text": "The fee is $0."}])
    assert len(fake_index.query_calls) == 1


def test_disk_cache_is_not_written_when_the_pinecone_read_fails(monkeypatch, tmp_path):
    class FailingIndex:
        def describe_index_stats(self) -> dict:
            raise RuntimeError("429 egress limit")

    cache_path = tmp_path / "corpus.json"
    monkeypatch.setattr(bm25_index, "get_index", lambda: FailingIndex())
    monkeypatch.setattr(bm25_index, "_disk_cache_path", cache_path)

    with pytest.raises(RuntimeError):
        _fetch_all_chunks()

    assert not cache_path.exists()


def test_no_disk_cache_unless_enabled(monkeypatch):
    fake_index = FakeIndex(dimension=1536, total_vector_count=0, matches=[])
    monkeypatch.setattr(bm25_index, "get_index", lambda: fake_index)
    monkeypatch.setattr(bm25_index, "_disk_cache_path", None)

    _fetch_all_chunks()
    _fetch_all_chunks()

    assert len(fake_index.query_calls) == 2


@pytest.fixture
def fake_corpus(monkeypatch):
    docs = [
        "The Scotiabank Passport has no foreign transaction fee.",
        "The Amex Cobalt earns five times points on dining.",
        "The RBC Avion transfers points to multiple airlines.",
    ]
    ids = ["scotia-passport-vi::fees", "amex-cobalt::rewards", "rbc-avion-vi::rewards"]
    metadatas = [{"text": d} for d in docs]
    tokenized = [_tokenize(d) for d in docs]
    corpus = Bm25Corpus(bm25=BM25Okapi(tokenized), ids=ids, metadatas=metadatas)
    monkeypatch.setattr(bm25_index, "_corpus", corpus)
    return corpus


def test_bm25_search_finds_keyword_match(fake_corpus):
    results = bm25_search("foreign transaction fee", top_k=3)
    assert results[0]["id"] == "scotia-passport-vi::fees"


def test_bm25_search_respects_top_k(fake_corpus):
    results = bm25_search("points", top_k=1)
    assert len(results) == 1


def test_bm25_search_returns_id_score_metadata_shape(fake_corpus):
    results = bm25_search("dining", top_k=1)
    assert set(results[0].keys()) == {"id", "score", "metadata"}


def test_bm25_search_empty_corpus(monkeypatch):
    # bm25_search short-circuits on an empty corpus before touching .bm25,
    # so a placeholder (never-constructed) BM25Okapi is fine here.
    monkeypatch.setattr(
        bm25_index,
        "_corpus",
        Bm25Corpus(bm25=None, ids=[], metadatas=[]),  # type: ignore[arg-type]
    )
    assert bm25_search("anything", top_k=5) == []


def test_the_keyword_index_is_read_from_the_configured_namespace(monkeypatch):
    fake_index = FakeIndex(
        dimension=1536,
        total_vector_count=16_852,  # two namespaces of 8,426
        matches=[],
        namespaces={"headers-v1": {"vector_count": 8426}, "": {"vector_count": 8426}},
    )
    monkeypatch.setattr(bm25_index, "get_index", lambda: fake_index)
    monkeypatch.setattr(
        bm25_index, "get_settings", lambda: type("S", (), {"pinecone_namespace": "headers-v1"})()
    )

    _fetch_all_chunks()

    call = fake_index.query_calls[0]
    assert call["namespace"] == "headers-v1"
    assert call["top_k"] == 8426  # the namespace's own count, not the index-wide total


def test_an_empty_namespace_setting_reads_the_default_section(monkeypatch):
    fake_index = FakeIndex(
        dimension=1536,
        total_vector_count=16_852,
        matches=[],
        namespaces={"headers-v1": {"vector_count": 8426}, "": {"vector_count": 8000}},
    )
    monkeypatch.setattr(bm25_index, "get_index", lambda: fake_index)
    monkeypatch.setattr(
        bm25_index, "get_settings", lambda: type("S", (), {"pinecone_namespace": ""})()
    )

    _fetch_all_chunks()

    call = fake_index.query_calls[0]
    assert call["namespace"] is None and call["top_k"] == 8000


def test_two_threads_asking_for_the_corpus_build_it_once(monkeypatch):
    import threading
    import time

    monkeypatch.setattr(bm25_index, "_corpus", None)
    builds: list[int] = []

    def slow_fetch():
        builds.append(1)
        time.sleep(0.05)
        return ["a::0"], [{"text": "alpha"}]

    monkeypatch.setattr(bm25_index, "_fetch_all_chunks", slow_fetch)
    threads = [threading.Thread(target=bm25_index.get_bm25_corpus) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(builds) == 1
