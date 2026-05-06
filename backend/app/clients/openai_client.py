"""OpenAI client for embeddings."""
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=30.0)
    return _client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def embed_text(text: str) -> list[float]:
    """Embed a single text into a vector. Retries on transient errors."""
    settings = get_settings()
    client = get_openai_client()
    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=text,
    )
    return response.data[0].embedding


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Used during ingestion."""
    settings = get_settings()
    client = get_openai_client()
    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=texts,
    )
    return [item.embedding for item in response.data]
