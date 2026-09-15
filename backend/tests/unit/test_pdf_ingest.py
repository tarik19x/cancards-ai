"""Unit tests for pdf_ingest — chunking and metadata logic, no Pinecone/OpenAI calls.

PDF extraction against real files is exercised only when a downloaded PDF is
present on disk (gitignored, not available in CI); the chunking and metadata
logic these tests focus on take plain text, so they run everywhere.
"""

import json
from pathlib import Path

import pytest

from app.models import Card
from app.rag.pdf_ingest import (
    PdfDocument,
    chunk_text,
    document_to_chunks,
    extract_pdf_text,
    find_pdf_documents,
    load_document_urls,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CARDS_PATH = DATA_DIR / "cards.json"
MANIFEST_PATH = DATA_DIR / "documents" / "manifest.json"
PDF_DIR = DATA_DIR / "documents" / "pdf"
SAMPLE_PDF = PDF_DIR / "scotia-passport-vi" / "insurance_certificate.pdf"


@pytest.fixture
def amex_cobalt() -> Card:
    raw = json.loads(CARDS_PATH.read_text(encoding="utf-8-sig"))
    card = next(c for c in raw if c["card_id"] == "amex-cobalt")
    return Card.model_validate(card)


def test_chunk_text_splits_long_document_with_overlap():
    text = (
        ("Section one covers the annual fee. " * 40)
        + "\n\n"
        + ("Section two covers foreign transaction fees. " * 40)
    )
    chunks = chunk_text(text)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 1000


def test_chunk_text_keeps_short_document_as_one_chunk():
    text = "This card has a $120 annual fee and no foreign transaction fee."
    chunks = chunk_text(text)
    assert chunks == [text]


def test_document_to_chunks_ids_and_metadata(amex_cobalt):
    doc = PdfDocument("amex-cobalt", "cardholder_agreement", Path("unused.pdf"))
    text = "Cardmember agreement terms. " * 60
    chunks = document_to_chunks(doc, text, amex_cobalt, "https://example.com/cma.pdf")

    assert len(chunks) > 0
    for i, chunk in enumerate(chunks):
        assert chunk["id"] == f"amex-cobalt::cardholder_agreement::{i}"
        assert chunk["section"] == "cardholder_agreement"
        meta = chunk["metadata"]
        assert meta["card_id"] == "amex-cobalt"
        assert meta["card_name"] == amex_cobalt.name
        assert meta["doc_type"] == "cardholder_agreement"
        assert meta["document_url"] == "https://example.com/cma.pdf"
        assert meta["chunk_index"] == i
        assert meta["text"] == chunk["text"]


def test_document_to_chunks_handles_missing_source_url(amex_cobalt):
    doc = PdfDocument("amex-cobalt", "benefit_guide", Path("unused.pdf"))
    chunks = document_to_chunks(doc, "Benefit guide text.", amex_cobalt, None)
    assert chunks[0]["metadata"]["document_url"] is None


def test_load_document_urls_keys_by_card_and_doc_type():
    urls = load_document_urls(MANIFEST_PATH)
    assert urls[("amex-cobalt", "cardholder_agreement")].startswith("https://")


def test_find_pdf_documents_matches_manifest_card_ids():
    if not PDF_DIR.exists():
        pytest.skip("PDFs not downloaded in this environment (gitignored)")
    known_cards = {c["card_id"] for c in json.loads(CARDS_PATH.read_text(encoding="utf-8-sig"))}
    docs = find_pdf_documents(PDF_DIR)
    assert len(docs) > 0
    for doc in docs:
        assert doc.card_id in known_cards


@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="PDF not downloaded in this environment")
def test_extract_pdf_text_returns_nonempty_prose():
    text = extract_pdf_text(SAMPLE_PDF)
    assert len(text) > 500
    assert "Scotiabank" in text
