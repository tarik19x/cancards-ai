"""Integration tests for FastAPI endpoints using httpx (no real external calls)."""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models import AnswerResponse, CardRecommendation, Citation


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_answer_response():
    return AnswerResponse(
        answer_markdown="The Scotiabank Passport has no FX fee.",
        recommended_cards=[
            CardRecommendation(
                card_id="scotia-passport-vi",
                card_name="Scotiabank Passport Visa Infinite",
                annual_fee_cad=150.0,
                why="Zero FX fee.",
                key_benefits=["0% FX fee"]
            )
        ],
        citations=[
            Citation(
                card_id="scotia-passport-vi",
                card_name="Scotiabank Passport Visa Infinite",
                issuer="Scotiabank",
                section="fees"
            )
        ],
        confidence_notes="Verified 2026-05-04",
        response_id="test-uuid",
        timestamp=datetime.now(timezone.utc),
    )


# ─── Health ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_returns_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert "timestamp" in data


# ─── Cards ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_cards_returns_five():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/cards")
    assert response.status_code == 200
    cards = response.json()
    assert len(cards) == 5


@pytest.mark.asyncio
async def test_get_specific_card():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/cards/amex-cobalt")
    assert response.status_code == 200
    card = response.json()
    assert card["card_id"] == "amex-cobalt"
    assert card["issuer"] == "American Express"


@pytest.mark.asyncio
async def test_get_unknown_card_returns_404():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/cards/not-a-real-card")
    assert response.status_code == 404


# ─── Ask ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ask_returns_valid_response(mock_answer_response):
    with (
        patch("app.routers.ask.retrieve_chunks", new_callable=AsyncMock) as mock_retrieve,
        patch("app.routers.ask.generate_response", new_callable=AsyncMock) as mock_generate,
    ):
        mock_retrieve.return_value = [{"id": "test", "score": 0.9, "metadata": {}}]
        mock_generate.return_value = mock_answer_response

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/ask",
                json={"question": "Which card has no foreign transaction fee?"}
            )

    assert response.status_code == 200
    data = response.json()
    assert "answer_markdown" in data
    assert "recommended_cards" in data
    assert "citations" in data
    assert "response_id" in data


@pytest.mark.asyncio
async def test_ask_validates_short_question():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/ask", json={"question": "hi"})
    assert response.status_code == 422  # Pydantic validation: min_length=3


@pytest.mark.asyncio
async def test_ask_returns_404_when_no_chunks_found():
    with patch("app.routers.ask.retrieve_chunks", new_callable=AsyncMock) as mock_retrieve:
        mock_retrieve.return_value = []  # Pinecone returned nothing

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/ask",
                json={"question": "What is the meaning of life?"}
            )

    assert response.status_code == 404
