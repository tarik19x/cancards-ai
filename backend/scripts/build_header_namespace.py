"""Build the card-name version of the corpus in its own Pinecone namespace (point 1m).

Point 1h found that most PDF chunks never say which card they belong to, so a
question naming a card can't tell that card's paragraph from its twins under
other cards. This writes "Card: <name>. Document: <type>." on top of every PDF
chunk before it is embedded and keyword-indexed.

The result goes in a separate namespace of the same index, not over the
original chunks: the live app keeps serving the original, and the "before"
state stays queryable so the final 100 can still be run against it.

The 250 per-card summary chunks are copied unchanged: they already open with the
card's name ("Scotiabank Momentum Visa Infinite Card fees: ..."). The chunk text
comes from the local corpus.json copy, so no Pinecone read and no PDFs are needed.

Dry run by default. Run with (from backend/):
  uv run python -m scripts.build_header_namespace                 # plan only, free
  uv run python -m scripts.build_header_namespace --write --limit 50   # small trial
  uv run python -m scripts.build_header_namespace --write         # everything

Rerunning is safe: chunks already in the namespace are skipped.
"""

import argparse
import asyncio
import json
from typing import Any

from app.clients.openai_client import embed_batch
from app.clients.pinecone_client import get_index, upsert_vectors
from scripts.recall_cache import CACHE_DIR

HEADER_NAMESPACE = "headers-v1"
CORPUS_PATH = CACHE_DIR / "corpus.json"

DOC_LABELS = {
    "cardholder_agreement": "cardholder agreement",
    "benefit_guide": "benefit guide",
    "insurance_certificate": "certificate of insurance",
}
EMBED_BATCH = 100
MAX_CHUNKS_PER_RUN = 9_000  # the corpus is about 8,400; a bigger number means something is wrong
PRICE_PER_MILLION_TOKENS = 0.02  # text-embedding-3-small; an estimate, not read from the bill


def header_text(meta: dict[str, Any]) -> str:
    """The text that gets embedded and keyword-indexed for one chunk."""
    label = DOC_LABELS.get(meta.get("doc_type", ""))
    if label is None:
        return meta["text"]
    return f"Card: {meta['card_name']}. Document: {label}.\n{meta['text']}"


def build_header_corpus(
    ids: list[str], metadatas: list[dict[str, Any]]
) -> tuple[list[str], list[dict[str, Any]]]:
    """Same chunks and ids, with each PDF chunk's text replaced by its header version."""
    return ids, [{**m, "text": header_text(m)} for m in metadatas]


def _existing_ids(namespace: str) -> set[str]:
    found: set[str] = set()
    for page in get_index().list(namespace=namespace):
        found.update(page)
    return found


async def _write(
    ids: list[str], metadatas: list[dict[str, Any]], namespace: str, limit: int | None
) -> None:
    done = _existing_ids(namespace)
    todo = [(i, m) for i, m in zip(ids, metadatas) if i not in done]
    if limit is not None:
        todo = todo[:limit]
    if len(todo) > MAX_CHUNKS_PER_RUN:
        raise SystemExit(f"{len(todo)} chunks to write is more than expected; stopping.")
    print(f"Already in '{namespace}': {len(done)}. Writing {len(todo)} more.", flush=True)
    for start in range(0, len(todo), EMBED_BATCH):
        batch = todo[start : start + EMBED_BATCH]
        embeddings = await embed_batch([m["text"] for _, m in batch])
        upsert_vectors(
            [{"id": i, "values": e, "metadata": m} for (i, m), e in zip(batch, embeddings)],
            namespace=namespace,
        )
        print(f"  wrote {min(start + EMBED_BATCH, len(todo))}/{len(todo)}", flush=True)
    stats = get_index().describe_index_stats()
    count = stats["namespaces"].get(namespace, {}).get("vector_count", 0)
    print(f"Namespace '{namespace}' now holds {count} vectors.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the card-name namespace")
    parser.add_argument("--write", action="store_true", help="Actually embed and upload")
    parser.add_argument("--limit", type=int, default=None, help="Only write this many (a trial)")
    parser.add_argument("--namespace", default=HEADER_NAMESPACE)
    args = parser.parse_args()

    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    ids, metadatas = build_header_corpus(corpus["ids"], corpus["metadatas"])
    changed = sum(1 for m, o in zip(metadatas, corpus["metadatas"]) if m["text"] != o["text"])
    tokens = sum(len(m["text"]) for m in metadatas) / 4  # rough: 4 characters a token
    print(f"Chunks: {len(ids)} ({changed} get a header, {len(ids) - changed} unchanged).")
    print(
        f"Embedding all of them: about {tokens / 1e6:.2f}M tokens, roughly "
        f"${tokens / 1e6 * PRICE_PER_MILLION_TOKENS:.3f} (estimate)."
    )
    example = next(m for m, o in zip(metadatas, corpus["metadatas"]) if m["text"] != o["text"])
    print(f"\nExample of a changed chunk:\n---\n{example['text'][:260]}\n---")

    if not args.write:
        print("\nDry run: nothing embedded or uploaded. Re-run with --write.")
        return
    asyncio.run(_write(ids, metadatas, args.namespace, args.limit))


if __name__ == "__main__":
    main()
