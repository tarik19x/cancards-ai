"""Tests for the card-name header rules -- no Pinecone or OpenAI calls."""

from scripts.build_header_namespace import build_header_corpus, header_text


def _pdf(doc_type: str = "insurance_certificate") -> dict:
    return {
        "card_id": "brim-world-elite",
        "card_name": "Brim World Elite Mastercard",
        "doc_type": doc_type,
        "text": "one (1) claim in any twelve (12) consecutive month period",
    }


def test_a_pdf_chunk_gets_the_card_name_and_document_type():
    text = header_text(_pdf())
    assert text.startswith("Card: Brim World Elite Mastercard. Document: certificate of insurance.")
    assert text.endswith("consecutive month period")


def test_every_document_type_has_a_readable_label():
    assert "cardholder agreement" in header_text(_pdf("cardholder_agreement"))
    assert "benefit guide" in header_text(_pdf("benefit_guide"))


def test_a_summary_chunk_is_left_unchanged_because_it_already_names_the_card():
    summary = {
        "card_id": "x",
        "card_name": "X Card",
        "section": "fees",
        "text": "X Card fees: Annual fee $0.",
    }
    assert header_text(summary) == "X Card fees: Annual fee $0."


def test_the_corpus_keeps_ids_order_and_every_other_field():
    ids = ["a::insurance_certificate::0", "a::fees"]
    metas = [_pdf(), {"card_id": "a", "card_name": "A", "section": "fees", "text": "A fees."}]
    new_ids, new_metas = build_header_corpus(ids, metas)

    assert new_ids == ids
    assert (
        new_metas[0]["card_id"] == "brim-world-elite" and new_metas[0]["text"] != metas[0]["text"]
    )
    assert new_metas[1] == metas[1]
    assert metas[0]["text"] == "one (1) claim in any twelve (12) consecutive month period"
