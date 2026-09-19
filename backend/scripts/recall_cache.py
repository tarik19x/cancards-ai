"""Disk cache for the recall harness's OpenAI and Pinecone calls.

Dev and production share one Pinecone account with a free monthly egress cap,
and repeated dev runs have taken the live site down once already. This makes
each question cost one embedding and one Pinecone query for the whole of
point 1, however many methods are compared.

Every Pinecone miss asks for the top POOL results and any smaller request is
served by slicing that list. That is only valid for a single ranked list, which
is what dense search returns; the hybrid and reranked methods are computed from
those slices locally (BM25 is local, RRF is arithmetic). It is the same
shortcut measure_recall.py's docstring explains for dense mode.

Saved Pinecone results are tagged with a hash of the local corpus copy. Once
the corpus changes (the 1m re-index means deleting corpus.json), the tag
no longer matches and the saved results are discarded rather than trusted.
Saved embeddings depend only on the question and the model, so they are kept.

Rerank results are saved too, keyed by the question and the exact text of every
candidate (plus the model), so a changed corpus can never reuse a stale ranking.
Each rerank is one billed Pinecone request against a small monthly allowance,
so a repeat costs nothing and a hard cap stops a runaway loop.

Dev scripts only. Nothing under app/ imports this.
"""

import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from scripts.llm_cache import BudgetExceeded

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"
POOL = 50
_SAVE_EVERY = 10

Embed = Callable[[str], Awaitable[list[float]]]
Query = Callable[..., list[dict[str, Any]]]
Rerank = Callable[[str, list[dict[str, Any]]], list[dict[str, Any]]]

# Pinecone allows 60 rerank requests a minute; stay just under it.
_MIN_SECONDS_BETWEEN_RERANKS = 1.1


def corpus_tag(corpus_path: Path) -> str:
    return hashlib.sha256(corpus_path.read_bytes()).hexdigest()[:16]


class RecallCache:
    def __init__(
        self,
        embed: Embed,
        query: Query,
        tag: str,
        embedding_model: str,
        embeddings_path: Path = CACHE_DIR / "recall_embeddings.json",
        queries_path: Path = CACHE_DIR / "recall_queries.json",
        max_paid_calls: int | None = None,
        rerank: Rerank | None = None,
        rerank_model: str = "",
        reranks_path: Path = CACHE_DIR / "recall_reranks.json",
        max_rerank_calls: int | None = None,
    ):
        self._embed = embed
        self._query = query
        self._tag = tag
        self._model = embedding_model
        self._embeddings_path = embeddings_path
        self._queries_path = queries_path
        self.max_paid_calls = max_paid_calls

        self._embeddings: dict[str, list[float]] = self._read(embeddings_path)
        saved = self._read(queries_path)
        self.queries_were_reset = bool(saved) and saved.get("tag") != tag
        self._queries: dict[str, list[dict[str, Any]]] = (
            saved.get("results", {}) if saved.get("tag") == tag else {}
        )
        self.embeds_paid = self.embeds_hit = self.queries_paid = self.queries_hit = 0
        self._unsaved = 0

        self._rerank = rerank
        self._rerank_model = rerank_model
        self._reranks_path = reranks_path
        self.max_rerank_calls = max_rerank_calls
        self._reranks: dict[str, list[dict[str, Any]]] = self._read(reranks_path)
        self.reranks_paid = self.reranks_hit = 0
        self._last_rerank_at = 0.0

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _check_budget(self) -> None:
        paid = self.embeds_paid + self.queries_paid
        if self.max_paid_calls is not None and paid >= self.max_paid_calls:
            raise BudgetExceeded(f"stopped at {paid} paid OpenAI/Pinecone calls")

    async def embed_text(self, text: str) -> list[float]:
        key = hashlib.sha256(f"{self._model}\n{text}".encode()).hexdigest()
        if key in self._embeddings:
            self.embeds_hit += 1
            return self._embeddings[key]
        self._check_budget()
        vector = await self._embed(text)
        self.embeds_paid += 1
        self._embeddings[key] = vector
        self._mark_dirty()
        return vector

    def query_vectors(
        self,
        embedding: list[float],
        top_k: int = 12,
        filter_dict: dict | None = None,
        namespace: str | None = None,
    ) -> list[dict[str, Any]]:
        # `namespace` comes from the app's settings, which the harness has set to the index
        # under test. Saved results are already kept in one file per index, so it is passed
        # to Pinecone on a miss but is not part of the key.
        if filter_dict is not None or top_k > POOL:
            self._check_budget()  # not sliceable from the saved pool, so pass it through
            self.queries_paid += 1
            return self._query(
                embedding=embedding, top_k=top_k, filter_dict=filter_dict, namespace=namespace
            )
        key = hashlib.sha256(json.dumps(embedding).encode()).hexdigest()
        if key in self._queries:
            self.queries_hit += 1
            return self._queries[key][:top_k]
        self._check_budget()
        results = self._query(embedding=embedding, top_k=POOL, namespace=namespace)
        self.queries_paid += 1
        self._queries[key] = results
        self._mark_dirty()
        return results[:top_k]

    def rerank_documents(self, query: str, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self._rerank is None:
            raise RuntimeError("this cache was built without a rerank function")
        blob = json.dumps(
            [
                self._rerank_model,
                query,
                [[d["id"], hashlib.sha256(d["text"].encode()).hexdigest()] for d in documents],
            ]
        )
        key = hashlib.sha256(blob.encode()).hexdigest()
        if key in self._reranks:
            self.reranks_hit += 1
            return self._reranks[key]
        if self.max_rerank_calls is not None and self.reranks_paid >= self.max_rerank_calls:
            raise BudgetExceeded(f"stopped at {self.reranks_paid} paid rerank requests")
        wait = self._last_rerank_at + _MIN_SECONDS_BETWEEN_RERANKS - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        result = self._rerank(query, documents)
        self._last_rerank_at = time.monotonic()
        self.reranks_paid += 1
        self._reranks[key] = result
        self._mark_dirty()
        return result

    def _mark_dirty(self) -> None:
        # Not every call: rewriting a file this size after each of ~100 misses
        # is slow, and flush() runs in a finally block so a crash keeps them.
        self._unsaved += 1
        if self._unsaved >= _SAVE_EVERY:
            self.flush()

    def flush(self) -> None:
        if not self._unsaved:
            return
        self._embeddings_path.parent.mkdir(parents=True, exist_ok=True)
        for path, payload in (
            (self._embeddings_path, self._embeddings),
            (self._queries_path, {"tag": self._tag, "results": self._queries}),
            (self._reranks_path, self._reranks),
        ):
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(path)
        self._unsaved = 0
