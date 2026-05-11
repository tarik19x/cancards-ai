"""Pinecone client for vector storage and retrieval."""

from pinecone import Pinecone, ServerlessSpec
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings

_pc: Pinecone | None = None
_index = None


def get_pinecone() -> Pinecone:
    global _pc
    if _pc is None:
        settings = get_settings()
        _pc = Pinecone(api_key=settings.pinecone_api_key)
    return _pc


def get_index():
    """Returns the Pinecone index, creating it if it doesn't exist."""
    global _index
    if _index is None:
        settings = get_settings()
        pc = get_pinecone()

        existing = [idx.name for idx in pc.list_indexes()]
        if settings.pinecone_index_name not in existing:
            pc.create_index(
                name=settings.pinecone_index_name,
                dimension=settings.embedding_dimensions,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud=settings.pinecone_cloud,
                    region=settings.pinecone_region,
                ),
            )
        _index = pc.Index(settings.pinecone_index_name)
    return _index


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def query_vectors(
    embedding: list[float],
    top_k: int = 12,
    filter_dict: dict | None = None,
) -> list[dict]:
    """Query Pinecone for top_k nearest neighbors."""
    index = get_index()
    response = index.query(
        vector=embedding,
        top_k=top_k,
        include_metadata=True,
        filter=filter_dict,
    )
    return [
        {
            "id": match["id"],
            "score": match["score"],
            "metadata": match["metadata"],
        }
        for match in response["matches"]
    ]


def upsert_vectors(vectors: list[dict]) -> None:
    """Upsert vectors. Each vector dict needs: id, values, metadata."""
    index = get_index()
    for i in range(0, len(vectors), 100):
        batch = vectors[i : i + 100]
        index.upsert(vectors=batch)
