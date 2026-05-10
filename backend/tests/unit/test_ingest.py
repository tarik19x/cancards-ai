"""Unit tests for card_to_chunks — no API calls, no Pinecone."""
import json
from pathlib import Path
import pytest
from app.models import Card
from app.rag.ingest import card_to_chunks


CARDS_PATH = Path(__file__).resolve().parents[2] / "data" / "cards.json"


@pytest.fixture
def sample_cards() -> list[Card]:
    raw = json.loads(CARDS_PATH.read_text(encoding="utf-8"))
    return [Card.model_validate(item) for item in raw]


@pytest.fixture
def amex_cobalt(sample_cards) -> Card:
    return next(c for c in sample_cards if c.card_id == "amex-cobalt")


@pytest.fixture
def scotiabank(sample_cards) -> Card:
    return next(c for c in sample_cards if c.card_id == "scotia-passport-vi")


def test_card_to_chunks_produces_five_chunks(amex_cobalt):
    chunks = card_to_chunks(amex_cobalt)
    assert len(chunks) == 5


def test_chunk_sections_are_correct(amex_cobalt):
    chunks = card_to_chunks(amex_cobalt)
    sections = {c["section"] for c in chunks}
    assert sections == {"overview", "rewards", "fees", "insurance", "eligibility"}


def test_chunk_ids_include_card_id(amex_cobalt):
    chunks = card_to_chunks(amex_cobalt)
    for chunk in chunks:
        assert chunk["id"].startswith("amex-cobalt::")


def test_chunk_metadata_has_required_fields(amex_cobalt):
    chunks = card_to_chunks(amex_cobalt)
    required_fields = {"card_id", "card_name", "issuer", "network", "annual_fee_cad", "section", "text"}
    for chunk in chunks:
        assert required_fields.issubset(chunk["metadata"].keys()), (
            f"Chunk {chunk['id']} missing fields: {required_fields - chunk['metadata'].keys()}"
        )


def test_fees_chunk_mentions_no_fx_for_scotiabank(scotiabank):
    chunks = card_to_chunks(scotiabank)
    fees_chunk = next(c for c in chunks if c["section"] == "fees")
    assert "NO foreign transaction fee" in fees_chunk["text"]


def test_fees_chunk_does_not_mention_no_fx_for_amex(amex_cobalt):
    chunks = card_to_chunks(amex_cobalt)
    fees_chunk = next(c for c in chunks if c["section"] == "fees")
    assert "NO foreign transaction fee" not in fees_chunk["text"]


def test_all_cards_produce_chunks(sample_cards):
    for card in sample_cards:
        chunks = card_to_chunks(card)
        assert len(chunks) == 5, f"{card.card_id} produced {len(chunks)} chunks instead of 5"


def test_chunk_text_is_non_empty(amex_cobalt):
    chunks = card_to_chunks(amex_cobalt)
    for chunk in chunks:
        assert len(chunk["text"]) > 20, f"Chunk {chunk['section']} text is suspiciously short"
