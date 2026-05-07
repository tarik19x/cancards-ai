"""Retrieve relevant card chunks from Pinecone given a user question."""
from app.clients.openai_client import embed_text
from app.clients.pinecone_client import query_vectors
from app.logging_config import get_logger
from langsmith import traceable

log = get_logger(__name__)


@traceable(name="retrieve_chunks", run_type="retriever")
async def retrieve_chunks(query: str, top_k: int = 12) -> list[dict]:
    """Embed the query and find top_k most relevant chunks."""
    embedding = await embed_text(query)
    matches = query_vectors(embedding=embedding, top_k=top_k)
    log.info("retrieved", query=query, count=len(matches))
    return matches
