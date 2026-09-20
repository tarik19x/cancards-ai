"""Anthropic client for Claude (LLM)."""

from collections.abc import AsyncIterator
from typing import Any

from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from app.clients.usage import meter
from app.config import get_settings

_client: AsyncAnthropic | None = None


def get_anthropic_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=60.0)
    return _client


def _cacheable_system(system_prompt: str) -> list[dict[str, Any]]:
    """The system prompt marked as a cache breakpoint.

    Every call sends the same long instructions. Marked like this, Anthropic keeps them for
    about five minutes and bills a re-read at a tenth of the input price (measured: a call
    dropped from about $0.0045 to $0.0014). The catch is a minimum size: a prompt shorter than
    1,024 tokens on Sonnet 4.6 is silently not cached, no error and no saving, so the extraction
    prompt is kept above that. If cache_read_input_tokens stays 0 in the usage log, the prompt
    has slipped under it or something in the prefix is changing between calls.
    """
    return [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]


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
        system=_cacheable_system(system_prompt),  # type: ignore[arg-type]
        messages=[{"role": "user", "content": user_prompt}],
    )
    meter.record(settings.llm_model, response.usage)
    return "".join(block.text for block in response.content if hasattr(block, "text"))


async def stream_answer(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2000,
) -> AsyncIterator[str]:
    """Streaming generation. Yields text chunks as they arrive."""
    settings = get_settings()
    client = get_anthropic_client()
    async with client.messages.stream(
        model=settings.llm_model,
        max_tokens=max_tokens,
        system=_cacheable_system(system_prompt),  # type: ignore[arg-type]
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        async for text in stream.text_stream:
            yield text
        meter.record(settings.llm_model, (await stream.get_final_message()).usage)
