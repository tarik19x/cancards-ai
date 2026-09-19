"""Unit tests for the dev-script Claude response cache -- fake generator, no API calls."""

import asyncio

from scripts.llm_cache import CachedGenerator


class FakeGenerate:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    async def __call__(self, system: str, user: str, max_tokens: int = 2000) -> str:
        self.calls.append((system, user, max_tokens))
        return f"answer-{len(self.calls)}"


def test_same_prompt_is_paid_for_once(tmp_path):
    fake = FakeGenerate()
    gen = CachedGenerator(fake, tmp_path / "c.json")

    first = asyncio.run(gen("sys", "user", max_tokens=400))
    second = asyncio.run(gen("sys", "user", max_tokens=400))

    assert first == second == "answer-1"
    assert (gen.calls_made, gen.cache_hits) == (1, 1)


def test_changed_prompt_or_max_tokens_misses_the_cache(tmp_path):
    fake = FakeGenerate()
    gen = CachedGenerator(fake, tmp_path / "c.json")

    asyncio.run(gen("sys", "user", max_tokens=400))
    asyncio.run(gen("sys v2", "user", max_tokens=400))
    asyncio.run(gen("sys", "user", max_tokens=5))

    assert gen.calls_made == 3
    assert gen.cache_hits == 0


def test_cache_survives_a_new_process(tmp_path):
    path = tmp_path / "c.json"
    asyncio.run(CachedGenerator(FakeGenerate(), path)("sys", "user", max_tokens=400))

    later_fake = FakeGenerate()
    later = CachedGenerator(later_fake, path)
    result = asyncio.run(later("sys", "user", max_tokens=400))

    assert result == "answer-1"
    assert later_fake.calls == []
    assert later.cache_hits == 1


def test_budget_stops_paid_calls_but_cached_ones_stay_free(tmp_path):
    import pytest

    from scripts.llm_cache import BudgetExceeded

    gen = CachedGenerator(FakeGenerate(), tmp_path / "c.json")
    gen.max_paid_calls = 1

    asyncio.run(gen("sys", "first", max_tokens=5))
    asyncio.run(gen("sys", "first", max_tokens=5))  # cached, not counted against the cap
    with pytest.raises(BudgetExceeded):
        asyncio.run(gen("sys", "second", max_tokens=5))

    assert gen.calls_made == 1
