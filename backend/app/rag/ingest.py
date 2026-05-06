"""Ingest the card database into Pinecone.

Each card becomes 5 chunks:
  - overview (name, issuer, fee, summary, best_for)
  - rewards (detailed earn rates)
  - fees (annual fee, FX fee)
  - insurance (full insurance breakdown)
  - eligibility (income, credit score)
"""
import json
from pathlib import Path

from app.clients.openai_client import embed_batch
from app.clients.pinecone_client import upsert_vectors
from app.logging_config import get_logger
from app.models import Card

log = get_logger(__name__)


def card_to_chunks(card: Card) -> list[dict]:
    """Convert a Card into multiple text chunks with metadata."""
    base_meta = {
        "card_id": card.card_id,
        "card_name": card.name,
        "issuer": card.issuer,
        "network": card.network,
        "annual_fee_cad": card.annual_fee_cad,
        "official_url": card.official_url,
    }

    chunks = [
        {
            "id": f"{card.card_id}::overview",
            "text": (
                f"{card.name} from {card.issuer} ({card.network}). "
                f"Annual fee: ${card.annual_fee_cad:.2f} CAD. "
                f"Rewards summary: {card.rewards_summary} "
                f"This card is best for: {', '.join(card.best_for)}. "
                f"Not ideal for: {', '.join(card.not_great_for)}. "
                f"Welcome bonus: {card.welcome_bonus_description or 'None'}."
            ),
            "section": "overview",
        },
        {
            "id": f"{card.card_id}::rewards",
            "text": (
                f"{card.name} rewards detail: {card.rewards_summary} "
                f"Detailed earn rates: "
                + "; ".join(
                    f"{cat}: {r.rate}{r.unit.replace('_', ' ')}"
                    + (f" (capped at ${r.monthly_cap_cad}/month)" if r.monthly_cap_cad else "")
                    for cat, r in card.rewards_detail.items()
                )
                + ". Estimated point value: "
                + (
                    f"{card.estimated_point_value_cents} cents per point."
                    if card.estimated_point_value_cents
                    else "N/A (cashback)."
                )
            ),
            "section": "rewards",
        },
        {
            "id": f"{card.card_id}::fees",
            "text": (
                f"{card.name} fees: Annual fee ${card.annual_fee_cad:.2f} CAD"
                + (f" (or ${card.monthly_fee_cad}/month)." if card.monthly_fee_cad else ".")
                + f" Foreign transaction fee: {card.foreign_transaction_fee_pct}%."
                + (
                    " This card has NO foreign transaction fee, making it strong for travel and online USD purchases."
                    if card.foreign_transaction_fee_pct == 0
                    else ""
                )
            ),
            "section": "fees",
        },
        {
            "id": f"{card.card_id}::insurance",
            "text": f"{card.name} insurance and benefits: {card.insurance_summary}",
            "section": "insurance",
        },
        {
            "id": f"{card.card_id}::eligibility",
            "text": (
                f"{card.name} eligibility: "
                + (
                    f"Recommended credit score {card.min_credit_score_recommended}+. "
                    if card.min_credit_score_recommended
                    else ""
                )
                + (
                    f"Minimum personal income: ${card.min_personal_income_cad:,.0f} CAD. "
                    if card.min_personal_income_cad
                    else ""
                )
                + (
                    f"Minimum household income: ${card.min_household_income_cad:,.0f} CAD. "
                    if card.min_household_income_cad
                    else ""
                )
            ),
            "section": "eligibility",
        },
    ]

    for chunk in chunks:
        chunk["metadata"] = {
            **base_meta,
            "section": chunk["section"],
            "text": chunk["text"],
        }
    return chunks


async def ingest_cards(cards_path: Path) -> int:
    """Read cards.json, chunk, embed, upsert to Pinecone. Returns count."""
    raw = json.loads(cards_path.read_text(encoding="utf-8-sig"))
    cards = [Card.model_validate(item) for item in raw]
    log.info("loaded_cards", count=len(cards))

    all_chunks = []
    for card in cards:
        all_chunks.extend(card_to_chunks(card))
    log.info("built_chunks", count=len(all_chunks))

    texts = [c["text"] for c in all_chunks]
    embeddings = []
    for i in range(0, len(texts), 100):
        batch = texts[i : i + 100]
        batch_emb = await embed_batch(batch)
        embeddings.extend(batch_emb)
        log.info("embedded_batch", from_idx=i, to_idx=i + len(batch))

    vectors = [
        {"id": chunk["id"], "values": emb, "metadata": chunk["metadata"]}
        for chunk, emb in zip(all_chunks, embeddings)
    ]

    upsert_vectors(vectors)
    log.info("upserted_vectors", count=len(vectors))
    return len(vectors)
