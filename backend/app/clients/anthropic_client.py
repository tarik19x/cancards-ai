"""Anthropic client for Claude (LLM)."""
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import get_settings


_client: AsyncAnthropic | None = None


def get_anthropic_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=60.0)
    return _client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def generate_answer(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2000,
) -> str:
    """Non-streaming generation."""
    settings = get_settings()
    client = get_anthropic_client()
    response = await client.messages.create(
        model=settings.llm_model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(
        block.text for block in response.content if hasattr(block, "text")
    )


async def stream_answer(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2000,
):
    """Streaming generation. Yields text chunks as they arrive."""
    settings = get_settings()
    client = get_anthropic_client()
    async with client.messages.stream(
        model=settings.llm_model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        async for text in stream.text_stream:
            yield text
