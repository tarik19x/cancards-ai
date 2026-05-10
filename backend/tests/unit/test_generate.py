"""Unit tests for parse_response and build_user_prompt."""
import json
from datetime import datetime, timezone
import pytest
from app.rag.generate import parse_response, build_user_prompt


VALID_RESPONSE = json.dumps({
    "answer_markdown": "The **Scotiabank Passport Visa Infinite** has no foreign transaction fee.",
    "recommended_cards": [
        {
            "card_id": "scotia-passport-vi",
            "card_name": "Scotiabank Passport Visa Infinite",
            "annual_fee_cad": 150.0,
            "why": "Zero FX fee, ideal for international travel.",
            "key_benefits": ["0% FX fee", "Lounge access", "25-day travel medical"]
        }
    ],
    "citations": [
        {
            "card_id": "scotia-passport-vi",
            "card_name": "Scotiabank Passport Visa Infinite",
            "issuer": "Scotiabank",
            "section": "fees"
        }
    ],
    "confidence_notes": "Verified as of 2026-05-04"
})


def test_parse_valid_response():
    result = parse_response(VALID_RESPONSE)
    assert result.answer_markdown.startswith("The **Scotiabank")
    assert len(result.recommended_cards) == 1
    assert result.recommended_cards[0].card_id == "scotia-passport-vi"
    assert len(result.citations) == 1
    assert result.citations[0].section == "fees"
    assert result.confidence_notes == "Verified as of 2026-05-04"
    assert result.response_id  # uuid was generated
    assert isinstance(result.timestamp, datetime)


def test_parse_response_with_code_fence():
    """Claude sometimes wraps JSON in backticks — parse_response should handle it."""
    fenced = f"```json\n{VALID_RESPONSE}\n```"
    result = parse_response(fenced)
    assert result.recommended_cards[0].card_id == "scotia-passport-vi"


def test_parse_response_empty_recommendations():
    raw = json.dumps({
        "answer_markdown": "Cannot find that information.",
        "recommended_cards": [],
        "citations": [],
        "confidence_notes": None
    })
    result = parse_response(raw)
    assert result.recommended_cards == []
    assert result.citations == []
    assert result.confidence_notes is None


def test_build_user_prompt_includes_question():
    chunks = [
        {
            "metadata": {
                "card_id": "amex-cobalt",
                "card_name": "American Express Cobalt Card",
                "issuer": "American Express",
                "section": "fees",
                "text": "Annual fee: $156 CAD. Foreign transaction fee: 2.5%."
            }
        }
    ]
    prompt = build_user_prompt("Which card has no FX fee?", chunks)
    assert "Which card has no FX fee?" in prompt
    assert "CONTEXT" in prompt
    assert "American Express Cobalt Card" in prompt
    assert "fees" in prompt


def test_build_user_prompt_numbers_chunks():
    chunks = [
        {"metadata": {"card_id": "a", "card_name": "A", "issuer": "I", "section": "fees", "text": "text a"}},
        {"metadata": {"card_id": "b", "card_name": "B", "issuer": "I", "section": "fees", "text": "text b"}},
    ]
    prompt = build_user_prompt("question?", chunks)
    assert "[1]" in prompt
    assert "[2]" in prompt
