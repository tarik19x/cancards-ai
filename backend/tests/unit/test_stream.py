"""Unit tests for the SSE streaming generator — no network, no keys.

The delimiter buffering and the trailing-JSON parsing are the two places where a
silent failure costs the user their recommendations, so both are pinned here.
"""

import json
from unittest.mock import patch

import pytest

from app.rag.stream import CARDS_DELIMITER, CITES_DELIMITER, stream_rag_response

CHUNKS = [
    {
        "metadata": {
            "card_id": "amex-cobalt",
            "card_name": "American Express Cobalt Card",
            "issuer": "American Express",
            "section": "rewards",
            "text": "Earn 5x points on eats and drinks.",
        }
    }
]

ANSWER = "The **Amex Cobalt** earns 5x on groceries and dining."

CARD_JSON = (
    '[{"card_id":"amex-cobalt","card_name":"American Express Cobalt Card",'
    '"annual_fee_cad":156,"why":"5x on eats.","key_benefits":["a","b","c"]}]'
)
CITE_JSON = (
    '[{"card_id":"amex-cobalt","card_name":"American Express Cobalt Card",'
    '"issuer":"American Express","section":"rewards"}]'
)


def build_reply(cards: str = CARD_JSON, cites: str = CITE_JSON, answer: str = ANSWER) -> str:
    return f"{answer}\n{CARDS_DELIMITER}\n{cards}\n{CITES_DELIMITER}\n{cites}"


async def collect(reply: str, chunk_size: int = 7) -> tuple[str, dict]:
    """Drive the generator with a reply sliced into fixed-size tokens.

    Small slices on purpose — they land delimiters across token boundaries,
    which is the case the buffering exists for.
    """

    async def fake_stream(system_prompt, user_prompt, max_tokens=2000):
        for i in range(0, len(reply), chunk_size):
            yield reply[i : i + chunk_size]

    streamed, done = "", None
    with patch("app.rag.stream.stream_answer", fake_stream):
        async for raw in stream_rag_response("best grocery card?", CHUNKS):
            event = json.loads(raw.removeprefix("data: ").strip())
            if event["type"] == "token":
                streamed += event["content"]
            else:
                done = event
    return streamed, done


# ─── Happy path ───────────────────────────────────────────────────────────────


async def test_streams_text_and_parses_both_sections():
    streamed, done = await collect(build_reply())

    assert streamed.strip() == ANSWER
    assert done["type"] == "done"
    assert done["chunks_used"] == len(CHUNKS)

    response = done["response"]
    assert response["answer_markdown"] == ANSWER
    assert len(response["recommended_cards"]) == 1
    assert response["recommended_cards"][0]["card_id"] == "amex-cobalt"
    assert len(response["citations"]) == 1


@pytest.mark.parametrize("chunk_size", [1, 3, 7, 11, 500])
async def test_delimiter_never_leaks_to_the_client(chunk_size):
    """No token slicing may push part of a sentinel into the visible text."""
    streamed, _ = await collect(build_reply(), chunk_size=chunk_size)

    assert CARDS_DELIMITER not in streamed
    assert CITES_DELIMITER not in streamed
    assert "===" not in streamed
    assert "card_id" not in streamed


# ─── Malformed output ─────────────────────────────────────────────────────────


async def test_trailing_commas_still_yield_recommendations():
    """Regression guard: the prompt template once taught Claude to emit these,
    and json.loads rejecting them silently emptied the panel."""
    sloppy = (
        '[{"card_id":"amex-cobalt","card_name":"American Express Cobalt Card",'
        '"annual_fee_cad":156,"why":"5x on eats.","key_benefits":["a","b","c",],},]'
    )
    _, done = await collect(build_reply(cards=sloppy))

    assert len(done["response"]["recommended_cards"]) == 1


async def test_unsalvageable_json_degrades_without_crashing():
    _, done = await collect(build_reply(cards='[{"card_id": '))

    assert done["type"] == "done"
    assert done["response"]["recommended_cards"] == []
    assert len(done["response"]["citations"]) == 1


async def test_one_invalid_card_does_not_drop_the_others():
    mixed = (
        '[{"card_id":"amex-cobalt","card_name":"American Express Cobalt Card",'
        '"annual_fee_cad":156,"why":"5x on eats.","key_benefits":["a"]},'
        '{"card_id":"broken"}]'
    )
    _, done = await collect(build_reply(cards=mixed))

    cards = done["response"]["recommended_cards"]
    assert len(cards) == 1
    assert cards[0]["card_id"] == "amex-cobalt"


# ─── Missing sections ─────────────────────────────────────────────────────────


async def test_missing_cards_delimiter_keeps_the_whole_answer():
    _, done = await collect(ANSWER)

    assert done["response"]["answer_markdown"] == ANSWER
    assert done["response"]["recommended_cards"] == []
    assert done["response"]["citations"] == []


async def test_missing_cites_delimiter_keeps_the_cards():
    _, done = await collect(f"{ANSWER}\n{CARDS_DELIMITER}\n{CARD_JSON}")

    assert len(done["response"]["recommended_cards"]) == 1
    assert done["response"]["citations"] == []


async def test_empty_arrays_are_valid():
    _, done = await collect(build_reply(cards="[]", cites="[]"))

    assert done["response"]["recommended_cards"] == []
    assert done["response"]["citations"] == []


# ─── Failure ──────────────────────────────────────────────────────────────────


async def test_upstream_error_becomes_an_error_event():
    async def exploding_stream(system_prompt, user_prompt, max_tokens=2000):
        yield "Partial answer"
        raise RuntimeError("upstream died")

    events = []
    with patch("app.rag.stream.stream_answer", exploding_stream):
        async for raw in stream_rag_response("q?", CHUNKS):
            events.append(json.loads(raw.removeprefix("data: ").strip()))

    assert events[-1]["type"] == "error"
    assert "upstream died" in events[-1]["message"]
