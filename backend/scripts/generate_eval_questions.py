"""Generate the point-1e eval question set for tests/evals/ground_truth.json.

50 single-card factual questions (one per card, rotating through the same
five sections ingest.py chunks a card into) plus a curated comparison subset
(7 two-card, 3 three-card) for point 3. Every fact is read from cards.json at
generation time and comparisons are asserted before being written, so a
future edit to cards.json either regenerates correct ground truth or fails
loudly here instead of leaving stale numbers in the eval set.

Also appends 11 hand-curated "pdf_grounded" questions. The first 60 only
test the short synthetic per-card summary -- every fact in them is also in
the card's "overview"/"rewards"/etc. chunk, which dense search already finds
almost perfectly (recall@8 0.986 on the first 60, see point 1f/1g). These 11
instead require a specific clause buried in the real cardholder agreement,
benefit guide, or certificate of insurance -- a grace period, a claim
deadline, a sub-limit -- that never appears in cards.json at all. That's the
part of the corpus hybrid search and reranking (points 1g/1h) actually exist
for, and the part the first 60 questions never exercised. Each one's exact
wording is asserted against the real extracted chunk before being written,
so a re-fetch or re-chunk of the PDFs that shifts an index fails loudly here
instead of silently mislabelling the eval set.

Run with:  python -m scripts.generate_eval_questions
"""

import json
from pathlib import Path
from typing import Any

from app.models import Card
from app.rag.pdf_ingest import chunk_text, extract_pdf_text

CARDS_PATH = Path(__file__).resolve().parents[1] / "data" / "cards.json"
PDF_DIR = Path(__file__).resolve().parents[1] / "data" / "documents" / "pdf"
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "tests" / "evals" / "ground_truth.json"

UNIT_DISPLAY = {
    "points_per_dollar": "points per dollar",
    "percent_cashback": "% cashback",
    "miles_per_dollar": "miles per dollar",
}

# These three cards' only "reward" is a 0%-rate low-interest placeholder --
# asking for their "highest reward rate" would be a nonsense question, so
# the round-robin below routes them to "overview" instead of "rewards".
NO_REWARDS_CARD_IDS = {"nb-syncro-mc", "mbna-true-line-mc", "cibc-select-visa"}


def load_cards() -> list[Card]:
    raw = json.loads(CARDS_PATH.read_text(encoding="utf-8-sig"))
    return [Card.model_validate(c) for c in raw]


def fmt_rate(rate: float, unit: str) -> str:
    unit_str = UNIT_DISPLAY[unit]
    return f"{rate}{unit_str}" if unit == "percent_cashback" else f"{rate} {unit_str}"


def fees_question(card: Card) -> dict[str, Any]:
    answer = f"The {card.name} has an annual fee of ${card.annual_fee_cad:,.2f} CAD"
    if card.monthly_fee_cad:
        answer += f" (or ${card.monthly_fee_cad:,.2f}/month)"
    answer += "."
    if card.foreign_transaction_fee_pct == 0:
        answer += " It also has no foreign transaction fee."
    return {
        "question": f"What is the annual fee for the {card.name}?",
        "ground_truth": answer,
        "relevant_card_ids": [card.card_id],
        "answering_chunk_ids": [f"{card.card_id}::fees"],
        "question_type": "single_card",
    }


def rewards_question(card: Card) -> dict[str, Any]:
    best_cat, best = max(card.rewards_detail.items(), key=lambda kv: kv[1].rate)
    rate_text = fmt_rate(best.rate, best.unit)
    if best.monthly_cap_cad:
        rate_text += f" (up to ${best.monthly_cap_cad:,.0f}/month)"
    elif best.annual_cap_cad:
        rate_text += f" (up to ${best.annual_cap_cad:,.0f}/year)"
    cat_display = best_cat.replace("_", " ")
    return {
        "question": (
            f"What is the highest rewards rate on the {card.name}, and which category earns it?"
        ),
        "ground_truth": f"The {card.name} earns its highest rate on {cat_display}: {rate_text}.",
        "relevant_card_ids": [card.card_id],
        "answering_chunk_ids": [f"{card.card_id}::rewards"],
        "question_type": "single_card",
    }


def insurance_question(card: Card) -> dict[str, Any]:
    ins = card.insurance_detail
    if ins.travel_emergency_medical_days:
        q = f"How many days of travel emergency medical coverage does the {card.name} provide?"
        a = (
            f"The {card.name} provides {ins.travel_emergency_medical_days} days "
            "of emergency medical coverage."
        )
    elif ins.lounge_access:
        q = f"Does the {card.name} include airport lounge access?"
        a = f"Yes, the {card.name} includes airport lounge access."
    elif ins.trip_cancellation:
        q = f"Does the {card.name} include trip cancellation insurance?"
        a = f"Yes, the {card.name} includes trip cancellation insurance."
    else:
        q = f"Does the {card.name} include purchase protection, and for how many days?"
        a = (
            f"Yes, the {card.name} includes purchase protection for "
            f"{ins.purchase_protection_days} days."
        )
    return {
        "question": q,
        "ground_truth": a,
        "relevant_card_ids": [card.card_id],
        "answering_chunk_ids": [f"{card.card_id}::insurance"],
        "question_type": "single_card",
    }


def eligibility_question(card: Card) -> dict[str, Any]:
    if card.min_credit_score_recommended:
        q = f"What is the minimum recommended credit score for the {card.name}?"
        a = (
            f"A credit score of {card.min_credit_score_recommended}+ is recommended "
            f"for the {card.name}."
        )
    elif card.min_personal_income_cad:
        q = f"What is the minimum personal income required for the {card.name}?"
        a = (
            f"A minimum personal income of ${card.min_personal_income_cad:,.0f} CAD "
            f"is required for the {card.name}."
        )
    else:
        q = f"Is there a minimum credit score or income requirement for the {card.name}?"
        a = f"No minimum credit score or income is specified for the {card.name}."
    return {
        "question": q,
        "ground_truth": a,
        "relevant_card_ids": [card.card_id],
        "answering_chunk_ids": [f"{card.card_id}::eligibility"],
        "question_type": "single_card",
    }


def overview_question(card: Card) -> dict[str, Any]:
    top = [t.replace("_", " ") for t in card.best_for[:3]]
    return {
        "question": f"What is the {card.name} best suited for?",
        "ground_truth": f"The {card.name} is best suited for: {', '.join(top)}.",
        "relevant_card_ids": [card.card_id],
        "answering_chunk_ids": [f"{card.card_id}::overview"],
        "question_type": "single_card",
    }


CATEGORY_BUILDERS = {
    "fees": fees_question,
    "rewards": rewards_question,
    "insurance": insurance_question,
    "eligibility": eligibility_question,
    "overview": overview_question,
}
ROTATION = ["fees", "rewards", "insurance", "eligibility", "overview"]


def build_single_card_questions(cards: list[Card]) -> list[dict[str, Any]]:
    questions = []
    for i, card in enumerate(cards):
        category = ROTATION[i % 5]
        if category == "rewards" and card.card_id in NO_REWARDS_CARD_IDS:
            category = "overview"
        questions.append(CATEGORY_BUILDERS[category](card))
    return questions


def build_comparison_questions(c: dict[str, Card]) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []

    # -- 7 two-card comparisons --------------------------------------------
    a, b = c["amex-cobalt"], c["scotia-passport-vi"]
    assert a.foreign_transaction_fee_pct > 0 and b.foreign_transaction_fee_pct == 0
    comparisons.append(
        {
            "question": (
                f"Which card has no foreign transaction fee: the {a.name} or the {b.name}?"
            ),
            "ground_truth": (
                f"The {b.name} has no foreign transaction fee (0%). "
                f"The {a.name} charges {a.foreign_transaction_fee_pct}%."
            ),
            "relevant_card_ids": [a.card_id, b.card_id],
            "answering_chunk_ids": [f"{a.card_id}::fees", f"{b.card_id}::fees"],
            "question_type": "comparison_2card",
        }
    )

    a, b = c["td-cash-back-vi"], c["rbc-cashback-mc"]
    assert a.annual_fee_cad > b.annual_fee_cad
    comparisons.append(
        {
            "question": f"Which has a lower annual fee: the {a.name} or the {b.name}?",
            "ground_truth": (
                f"The {b.name} has a lower annual fee at ${b.annual_fee_cad:,.2f} CAD, "
                f"versus ${a.annual_fee_cad:,.2f} CAD for the {a.name}."
            ),
            "relevant_card_ids": [a.card_id, b.card_id],
            "answering_chunk_ids": [f"{a.card_id}::fees", f"{b.card_id}::fees"],
            "question_type": "comparison_2card",
        }
    )

    a, b = c["amex-platinum"], c["scotia-platinum-amex"]
    assert a.annual_fee_cad > b.annual_fee_cad
    diff = a.annual_fee_cad - b.annual_fee_cad
    comparisons.append(
        {
            "question": (
                f"How much cheaper is the {b.name}'s annual fee compared to the {a.name}?"
            ),
            "ground_truth": (
                f"The {b.name} is ${diff:,.2f} CAD cheaper: ${b.annual_fee_cad:,.2f} "
                f"versus ${a.annual_fee_cad:,.2f} for the {a.name}."
            ),
            "relevant_card_ids": [a.card_id, b.card_id],
            "answering_chunk_ids": [f"{a.card_id}::fees", f"{b.card_id}::fees"],
            "question_type": "comparison_2card",
        }
    )

    a, b = c["rbc-westjet-world-elite"], c["rbc-westjet-mc"]
    rate_a = a.rewards_detail["westjet_purchases"].rate
    rate_b = b.rewards_detail["westjet_purchases"].rate
    assert rate_a > rate_b
    comparisons.append(
        {
            "question": (
                "Which WestJet RBC card earns a higher cashback rate on WestJet "
                "purchases, and what is the rate?"
            ),
            "ground_truth": (
                f"The {a.name} earns {rate_a}% WestJet dollars on WestJet purchases, "
                f"higher than the {b.name}'s {rate_b}%."
            ),
            "relevant_card_ids": [a.card_id, b.card_id],
            "answering_chunk_ids": [f"{a.card_id}::rewards", f"{b.card_id}::rewards"],
            "question_type": "comparison_2card",
        }
    )

    a, b = c["brim-world-elite"], c["brim-world-mc"]
    assert a.insurance_detail.lounge_access and not b.insurance_detail.lounge_access
    comparisons.append(
        {
            "question": "Which Brim Mastercard includes airport lounge access?",
            "ground_truth": (
                f"The {a.name} includes unlimited airport lounge access via DragonPass; "
                f"the {b.name} does not include lounge access."
            ),
            "relevant_card_ids": [a.card_id, b.card_id],
            "answering_chunk_ids": [f"{a.card_id}::insurance", f"{b.card_id}::insurance"],
            "question_type": "comparison_2card",
        }
    )

    a, b = c["desjardins-odyssey-world-elite"], c["nb-world-elite-mc"]
    assert a.annual_fee_cad < b.annual_fee_cad
    comparisons.append(
        {
            "question": f"Which has a lower annual fee: the {a.name} or the {b.name}?",
            "ground_truth": (
                f"The {a.name} has a lower annual fee at ${a.annual_fee_cad:,.2f} CAD, "
                f"versus ${b.annual_fee_cad:,.2f} CAD for the {b.name}."
            ),
            "relevant_card_ids": [a.card_id, b.card_id],
            "answering_chunk_ids": [f"{a.card_id}::fees", f"{b.card_id}::fees"],
            "question_type": "comparison_2card",
        }
    )

    a, b = c["home-trust-preferred-visa"], c["rogers-red-mc"]
    assert a.foreign_transaction_fee_pct == 0 and b.foreign_transaction_fee_pct > 0
    comparisons.append(
        {
            "question": (
                "Which of these two no-annual-fee cards has a true 0% foreign "
                f"transaction fee: the {a.name} or the {b.name}?"
            ),
            "ground_truth": (
                f"The {a.name} has a 0% foreign transaction fee. The {b.name} charges "
                f"the standard {b.foreign_transaction_fee_pct}%, offset by 3% cashback "
                "on US dollar purchases."
            ),
            "relevant_card_ids": [a.card_id, b.card_id],
            "answering_chunk_ids": [f"{a.card_id}::fees", f"{b.card_id}::fees"],
            "question_type": "comparison_2card",
        }
    )

    # -- 3 three-card comparisons (harder: multi-way, one is a real tie) ---
    a, b, cc = c["amex-cobalt"], c["scotia-gold-amex"], c["bmo-eclipse-vi"]
    rate_a = a.rewards_detail["eat_and_drink"].rate
    rate_b_sobeys = b.rewards_detail["sobeys_group_grocery"].rate
    rate_b_other = b.rewards_detail["other_grocery_dining_delivery"].rate
    rate_cc = cc.rewards_detail["grocery_dining_gas_pharmacy"].rate
    assert rate_b_sobeys > rate_a == rate_cc == rate_b_other
    comparisons.append(
        {
            "question": (
                f"Of the {a.name}, {b.name}, and {cc.name}, which earns the "
                "highest points rate on groceries?"
            ),
            "ground_truth": (
                f"The {b.name} earns the highest rate at Sobeys-group grocery stores "
                f"({rate_b_sobeys}x Scene+ points per dollar); it earns {rate_b_other}x at "
                f"other grocery stores, the same top rate as the {a.name} ({rate_a}x on "
                f"eat and drink, which includes eligible grocery stores) and the {cc.name} "
                f"({rate_cc}x on grocery, dining, gas, and pharmacy)."
            ),
            "relevant_card_ids": [a.card_id, b.card_id, cc.card_id],
            "answering_chunk_ids": [
                f"{a.card_id}::rewards",
                f"{b.card_id}::rewards",
                f"{cc.card_id}::rewards",
            ],
            "question_type": "comparison_3card",
        }
    )

    a, b, cc = c["rbc-avion-vi"], c["cibc-aventura-vi"], c["td-first-class-vi"]
    assert a.annual_fee_cad < b.annual_fee_cad == cc.annual_fee_cad
    comparisons.append(
        {
            "question": (
                f"Of the {a.name}, {b.name}, and {cc.name}, which has the lowest annual fee?"
            ),
            "ground_truth": (
                f"The {a.name} has the lowest annual fee at ${a.annual_fee_cad:,.2f} CAD. "
                f"Both the {b.name} and {cc.name} charge ${b.annual_fee_cad:,.2f} CAD."
            ),
            "relevant_card_ids": [a.card_id, b.card_id, cc.card_id],
            "answering_chunk_ids": [
                f"{a.card_id}::fees",
                f"{b.card_id}::fees",
                f"{cc.card_id}::fees",
            ],
            "question_type": "comparison_3card",
        }
    )

    a, b, cc = (
        c["amex-aeroplan-reserve"],
        c["cibc-aeroplan-vi-privilege"],
        c["td-aeroplan-vi-privilege"],
    )
    assert a.annual_fee_cad == b.annual_fee_cad == cc.annual_fee_cad
    comparisons.append(
        {
            "question": (
                f"Of the {a.name}, {b.name}, and {cc.name}, which has the highest annual fee?"
            ),
            "ground_truth": (
                "None -- all three of these premium Aeroplan cards, from three "
                f"different issuers, charge the same ${a.annual_fee_cad:,.2f} CAD "
                "annual fee."
            ),
            "relevant_card_ids": [a.card_id, b.card_id, cc.card_id],
            "answering_chunk_ids": [
                f"{a.card_id}::fees",
                f"{b.card_id}::fees",
                f"{cc.card_id}::fees",
            ],
            "question_type": "comparison_3card",
        }
    )

    return comparisons


# Each entry: (card_id, doc_type, chunk_index, question, ground_truth,
# must_contain). must_contain is a short, distinctive phrase that has to be
# present in the actual chunk at chunk_index -- checked below before the
# question is written, so a stale index fails loudly instead of silently
# mislabelling the eval set.
PDF_GROUNDED_SPECS: list[tuple[str, str, int, str, str, str]] = [
    (
        "amex-platinum",
        "cardholder_agreement",
        30,
        "According to its cardholder agreement, what is the standard payment "
        "grace period on the American Express Platinum Card, and how far can "
        "it extend if a payment isn't received in full by the due date?",
        "The standard grace period is 21 days. If payment in full isn't "
        "received by the due date, the grace period on the next statement "
        "extends to up to 25 days.",
        "revert to 21 days",
    ),
    (
        "cibc-costco-mc",
        "benefit_guide",
        5,
        "What is the overlimit fee on the CIBC Costco Mastercard, according "
        "to its summary of interest rates and fees?",
        "$29, charged once per statement period if the balance goes over the "
        "credit limit (not applicable to Quebec residents).",
        "Overlimit fee: $29",
    ),
    (
        "cibc-costco-mc",
        "benefit_guide",
        0,
        "What is the standard annual interest rate on purchases for the "
        "CIBC Costco Mastercard, according to its summary of interest rates "
        "and fees?",
        "21.75% per year.",
        "21.75%",
    ),
    (
        "rbc-avion-vi",
        "cardholder_agreement",
        33,
        "What is the dishonoured payment fee on the RBC Avion Visa Infinite, "
        "according to its cardholder agreement?",
        "$45, charged when a payment isn't processed because a bank returns "
        "a cheque or refuses a pre-authorized debit.",
        "Dishonoured Payment Fee",
    ),
    (
        "rbc-avion-vi",
        "cardholder_agreement",
        28,
        "How much advance written notice must RBC give before increasing the "
        "standard interest rate on the RBC Avion Visa Infinite, according to "
        "its cardholder agreement?",
        "At least 30 days written notice (except for increases caused by a "
        "rise in RBC's Prime Rate).",
        "30 days written notice",
    ),
    (
        "brim-world-elite",
        "insurance_certificate",
        44,
        "How many mobile device insurance claims can a Brim World Elite "
        "Mastercard cardholder make in a 12-month period, and what's the cap "
        "over any 48-month period?",
        "One claim in any 12 consecutive months, up to a maximum of two "
        "claims in any 48 consecutive months.",
        "twelve (12) consecutive month period",
    ),
    (
        "brim-world-elite",
        "insurance_certificate",
        97,
        "What is the overall emergency medical insurance coverage maximum "
        "on the Brim World Elite Mastercard, according to its certificate "
        "of insurance?",
        "$5,000,000 for reasonable and customary expenses arising from an "
        "unexpected sickness, injury, or medical condition.",
        "$5,000,000",
    ),
    (
        "brim-world-elite",
        "insurance_certificate",
        139,
        "What is the maximum rental period for a car to be eligible under "
        "the Brim World Elite Mastercard's Car Rental Collision/Loss Damage "
        "Insurance?",
        "The total rental period must not exceed 48 days.",
        "does not exceed forty",
    ),
    (
        "td-first-class-vi",
        "cardholder_agreement",
        117,
        "What is the accidental dental coverage limit under the TD First "
        "Class Travel Visa Infinite's travel insurance, and what is the "
        "separate cap for emergency dental pain relief?",
        "Up to $2,000 for dental treatment necessitated by a blow to the "
        "teeth during the coverage period; emergency relief of dental pain "
        "is capped separately at $200.",
        "up to $2,000 for dental",
    ),
    (
        "scotia-passport-vi",
        "insurance_certificate",
        97,
        "What is the maximum benefit for 'Return of Deceased' coverage "
        "under the Scotiabank Passport Visa Infinite's travel insurance?",
        "A maximum of $5,000 for the cost of preparation (including "
        "cremation) and transport of the insured person to their province "
        "or territory of residence in Canada.",
        "Return of Deceased",
    ),
    (
        "desjardins-odyssey-world-elite",
        "insurance_certificate",
        11,
        "For a mobile device insurance claim on the Desjardins Odyssey "
        "World Elite Mastercard, how many days does the cardholder have to "
        "call the insurer, and how many days to notify police in case of "
        "theft?",
        "The cardholder must call the insurer within 14 days from the date "
        "of loss, and in the case of theft, must notify the police within "
        "seven days of the date of loss.",
        "within 14 days from the date of loss",
    ),
]


def build_pdf_grounded_questions() -> list[dict[str, Any]]:
    questions = []
    chunk_cache: dict[tuple[str, str], list[str]] = {}
    for card_id, doc_type, idx, question, ground_truth, must_contain in PDF_GROUNDED_SPECS:
        key = (card_id, doc_type)
        if key not in chunk_cache:
            path = PDF_DIR / card_id / f"{doc_type}.pdf"
            chunk_cache[key] = chunk_text(extract_pdf_text(path))
        chunk = chunk_cache[key][idx]
        assert must_contain in chunk, (
            f"{card_id}::{doc_type}::{idx} no longer contains {must_contain!r} -- "
            "the PDF or chunking changed; re-locate this fact before regenerating"
        )
        questions.append(
            {
                "question": question,
                "ground_truth": ground_truth,
                "relevant_card_ids": [card_id],
                "answering_chunk_ids": [f"{card_id}::{doc_type}::{idx}"],
                "question_type": "pdf_grounded",
            }
        )
    return questions


def main() -> None:
    cards = load_cards()
    assert len(cards) == 50, f"expected 50 cards, found {len(cards)}"
    cards_by_id = {c.card_id: c for c in cards}

    single_card = build_single_card_questions(cards)
    comparisons = build_comparison_questions(cards_by_id)
    pdf_grounded = build_pdf_grounded_questions()
    questions = single_card + comparisons + pdf_grounded

    assert len(single_card) == 50
    assert len(comparisons) == 10
    assert len(pdf_grounded) == 11
    assert len(questions) == 71

    if OUTPUT_PATH.exists() and any(
        q.get("eval_set") == "hard" for q in json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    ):
        # This script rebuilds only the 71 easy/pilot questions; running it after the
        # merge would silently delete the frozen hard set.
        raise SystemExit("ground_truth.json holds the frozen hard set; refusing to overwrite it.")
    OUTPUT_PATH.write_text(json.dumps(questions, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(questions)} questions to {OUTPUT_PATH}")
    print(f"  single_card: {len(single_card)}")
    print(f"  pdf_grounded: {len(pdf_grounded)}")
    two_card = sum(1 for q in comparisons if q["question_type"] == "comparison_2card")
    three_card = sum(1 for q in comparisons if q["question_type"] == "comparison_3card")
    print(f"  comparison_2card: {two_card}")
    print(f"  comparison_3card: {three_card}")


if __name__ == "__main__":
    main()
