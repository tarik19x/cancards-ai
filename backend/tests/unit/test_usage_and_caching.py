"""The cost meter's arithmetic and the prompt-caching request shape -- fakes only, no API calls."""

import json
from types import SimpleNamespace

import pytest

from app.clients import anthropic_client
from app.clients.usage import UsageMeter


def _usage(fresh=0, out=0, written=0, read=0):
    return SimpleNamespace(
        input_tokens=fresh,
        output_tokens=out,
        cache_creation_input_tokens=written,
        cache_read_input_tokens=read,
    )


def test_a_plain_call_is_priced_at_input_plus_output_rates():
    meter = UsageMeter()
    # Sonnet 4.6: $3 in, $15 out per million.
    meter.record("claude-sonnet-4-6", _usage(fresh=1_000_000, out=1_000_000))
    assert meter.cost_usd == pytest.approx(18.00)
    assert meter.calls == 1


def test_cache_reads_cost_a_tenth_and_writes_a_quarter_more():
    meter = UsageMeter()
    meter.record("claude-sonnet-4-6", _usage(read=1_000_000))
    assert meter.cost_usd == pytest.approx(0.30)
    meter.reset()
    meter.record("claude-sonnet-4-6", _usage(written=1_000_000))
    assert meter.cost_usd == pytest.approx(3.75)


def test_the_measured_call_from_the_live_test_prices_as_it_did_on_the_bill():
    # Real numbers from one live check: 36 fresh + 1162 read + 60 output tokens was $0.00136.
    meter = UsageMeter()
    meter.record("claude-sonnet-4-6", _usage(fresh=36, read=1162, out=60))
    assert meter.cost_usd == pytest.approx(0.00136, abs=0.00001)


def test_missing_cache_fields_count_as_zero():
    meter = UsageMeter()
    meter.record("claude-sonnet-4-6", SimpleNamespace(input_tokens=10, output_tokens=5))
    assert meter.cache_read_tokens == 0 and meter.cache_write_tokens == 0

    meter.record("claude-sonnet-4-6", _usage(fresh=10, out=5, written=None, read=None))
    assert meter.calls == 2


def test_an_unlisted_model_is_priced_like_sonnet_and_flagged_not_free():
    meter = UsageMeter()
    meter.record("claude-something-new", _usage(fresh=1_000_000))
    assert meter.cost_usd == pytest.approx(3.00)
    assert meter.snapshot()["prices_assumed_for"] == ["claude-something-new"]
    assert "assumed" in meter.summary()


def test_the_summary_says_how_much_came_from_the_cache():
    meter = UsageMeter()
    meter.record("claude-sonnet-4-6", _usage(fresh=100, read=900, out=10))
    assert "90% of input read from cache" in meter.summary()


def test_each_run_can_be_appended_to_a_local_log(tmp_path):
    meter = UsageMeter()
    meter.record("claude-sonnet-4-6", _usage(fresh=100, out=10))
    log = tmp_path / "usage.jsonl"

    meter.append_to_log("scenarios", log)
    meter.append_to_log("attacks", log)

    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [line["label"] for line in lines] == ["scenarios", "attacks"]
    assert lines[0]["calls"] == 1 and "at" in lines[0]


class _FakeMessages:
    def __init__(self):
        self.kwargs: dict = {}

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(text="hello")], usage=_usage(fresh=20, read=1000, out=5)
        )


async def test_the_system_prompt_is_sent_as_a_cache_breakpoint_and_usage_is_recorded(monkeypatch):
    messages = _FakeMessages()
    monkeypatch.setattr(
        anthropic_client, "get_anthropic_client", lambda: SimpleNamespace(messages=messages)
    )
    monkeypatch.setattr(anthropic_client, "meter", UsageMeter())

    reply = await anthropic_client.generate_answer("LONG INSTRUCTIONS", "the question")

    assert reply == "hello"
    assert messages.kwargs["system"] == [
        {"type": "text", "text": "LONG INSTRUCTIONS", "cache_control": {"type": "ephemeral"}}
    ]
    assert messages.kwargs["messages"] == [{"role": "user", "content": "the question"}]
    assert anthropic_client.meter.cache_read_tokens == 1000


async def test_the_extraction_prompt_stays_above_the_cache_minimum():
    # Sonnet 4.6 silently skips caching below 1,024 tokens. Measured with the token counter: this
    # prompt is 3,946 characters and about 1,165 tokens (3.4 characters per token). The floor
    # below guards against trimming it back under the line, where the saving (about 70% per
    # extraction call, measured) would vanish with no error anywhere.
    from app.coach.profile import EXTRACT_SYSTEM_PROMPT

    assert len(EXTRACT_SYSTEM_PROMPT) >= 3900, "extraction prompt is nearing the 1,024-token floor"
