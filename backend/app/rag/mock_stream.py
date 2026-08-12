"""Fake SSE stream for UI development. Zero API cost — no OpenAI embed,
no Pinecone query, no Claude call. Same event shape as the real stream,
so the frontend can't tell the difference.
"""
import asyncio
import json
import random
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

CARDS_PATH = Path(__file__).resolve().parents[2] / "data" / "cards.json"

MOCK_ANSWER = (
    "Great question! For **grocery spending**, two cards stand out. "
    "The **Scotia Momentum Visa Infinite** earns 4% cash back on groceries "
    "with a $120 annual fee, while the **Tangerine Money-Back** lets you "
    "pick your own 2% categories with no fee at all.\n\n"
    "If your grocery spend is over $250 a month, Momentum pulls ahead. "
    "Below that, Tangerine's flexibility usually wins."
)


def _load_two_real_cards() -> list[dict]:
    """Pull real card_ids from cards.json so downstream fetches
    (InsightPanel hitting /api/cards/{id}) resolve to actual data
    instead of 404ing on a fake id."""
    with open(CARDS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    cards = data if isinstance(data, list) else list(data.values())[0]
    return random.sample(cards, k=min(2, len(cards)))


async def stream_mock_response(question: str) -> AsyncIterator[str]:
    """Same event contract as stream_rag_response: token events, then
    one done event, then nothing. Delays are there on purpose — a
    stream that returns instantly hides layout bugs in the loading state.
    """
    response_id = str(uuid.uuid4())
    words = MOCK_ANSWER.split(" ")

    for word in words:
        await asyncio.sleep(0.03)
        yield f"data: {json.dumps({'type': 'token', 'content': word + ' '})}\n\n"

    cards = _load_two_real_cards()
    recommended_cards = [
        {
            "card_id": cards[0]["card_id"],
            "card_name": cards[0]["name"],
            "annual_fee_cad": cards[0]["annual_fee_cad"],
            "why": "Best match for your grocery spend based on the mock scenario.",
            "key_benefits": [
                "Strong grocery earn rate",
                "No foreign transaction surprises",
                "Widely accepted network",
            ],
        },
        {
            "card_id": cards[1]["card_id"],
            "card_name": cards[1]["name"],
            "annual_fee_cad": cards[1]["annual_fee_cad"],
            "why": "Solid no-fee runner-up for lighter spenders.",
            "key_benefits": [
                "No annual fee",
                "Flexible category selection",
                "Easy approval bar",
            ],
        },
    ]

    citations = [
        {"card_id": cards[0]["card_id"], "card_name": cards[0]["name"], "issuer": cards[0]["issuer"], "section": "rewards"},
        {"card_id": cards[1]["card_id"], "card_name": cards[1]["name"], "issuer": cards[1]["issuer"], "section": "fees"},
    ]

    response = {
        "answer_markdown": MOCK_ANSWER,
        "recommended_cards": recommended_cards,
        "citations": citations,
        "confidence_notes": None,
        "response_id": response_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    done_event = {
        "type": "done",
        "response": response,
        "chunks_used": random.randint(8, 12),  # varies so the metric doesn't look hardcoded
    }
    yield f"data: {json.dumps(done_event)}\n\n"