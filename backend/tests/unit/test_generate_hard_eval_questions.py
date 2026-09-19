"""Unit tests for the hard-eval-question candidate finders (script for point
1j) -- no LLM or Pinecone calls. Only the pure selection/verification logic
is tested here; draft_question() itself is a real Claude call and is
reviewed by hand instead (see the module docstring).
"""

import pytest

from app.models import Card
from scripts.generate_hard_eval_questions import (
    UNANSWERABLE_SPECS,
    _complete_sentences,
    _cross_source_grounded,
    _grounded,
    _mentions_own_card,
    _shared_bigrams,
    _stable_rank,
    build_unanswerable,
    find_cross_source_candidates,
    find_disambiguation_candidates,
    find_exact_term_candidates,
    find_exclusion_candidates,
    pdf_chunks,
)


def make_chunk(
    card_id: str, doc_type: str, text: str, chunk_index: int = 0, card_name: str | None = None
) -> tuple[str, dict]:
    return (
        f"{card_id}::{doc_type}::{chunk_index}",
        {
            "card_id": card_id,
            "card_name": card_name if card_name is not None else card_id,
            "doc_type": doc_type,
            "chunk_index": chunk_index,
            "text": text,
        },
    )


def test_stable_rank_is_deterministic():
    assert _stable_rank("some-id") == _stable_rank("some-id")


def test_stable_rank_differs_for_different_ids():
    assert _stable_rank("a") != _stable_rank("b")


def test_pdf_chunks_excludes_card_summary_chunks():
    class FakeCorpus:
        ids = ["amex-cobalt::fees", "amex-cobalt::cardholder_agreement::0"]
        metadatas = [{"doc_type": "fees"}, {"doc_type": "cardholder_agreement"}]

    result = pdf_chunks(FakeCorpus())
    assert result == [
        ("amex-cobalt::cardholder_agreement::0", {"doc_type": "cardholder_agreement"})
    ]


def test_find_exact_term_candidates_matches_dollar_percent_and_days():
    chunks = [
        make_chunk("amex-cobalt", "cardholder_agreement", "The overlimit fee is $29."),
        make_chunk("rbc-avion-vi", "insurance_certificate", "Coverage extends for 25 days."),
        make_chunk("td-first-class-vi", "benefit_guide", "No numeric fact lives in this sentence."),
    ]
    found = find_exact_term_candidates(chunks)
    ids = {cid for cid, _meta, _facts in found}
    assert ids == {"amex-cobalt::cardholder_agreement::0", "rbc-avion-vi::insurance_certificate::0"}


def test_find_exact_term_candidates_returns_the_matched_facts():
    chunks = [
        make_chunk("amex-cobalt", "cardholder_agreement", "The fee is $29 plus a 2.5% surcharge.")
    ]
    (_cid, _meta, facts) = find_exact_term_candidates(chunks)[0]
    assert "$29" in facts
    assert "2.5%" in facts


def test_find_exclusion_candidates_matches_known_phrases():
    chunks = [
        make_chunk(
            "amex-cobalt",
            "insurance_certificate",
            "This policy does not cover pre-existing conditions.",
        ),
        make_chunk("rbc-avion-vi", "insurance_certificate", "This benefit is available worldwide."),
    ]
    found = find_exclusion_candidates(chunks)
    assert [cid for cid, _meta in found] == ["amex-cobalt::insurance_certificate::0"]


def test_find_disambiguation_candidates_finds_cross_card_near_duplicates():
    shared_text = " ".join(f"word{i}" for i in range(40))
    chunks = [
        make_chunk("brim-world-elite", "insurance_certificate", shared_text),
        make_chunk("rbc-westjet-mc", "insurance_certificate", shared_text),
        make_chunk(
            "amex-cobalt",
            "cardholder_agreement",
            "completely unrelated text about a different topic",
        ),
    ]
    pairs = find_disambiguation_candidates(chunks, min_jaccard=0.6)
    assert len(pairs) == 1
    (chunk_a, chunk_b, jaccard) = pairs[0]
    assert {chunk_a[1]["card_id"], chunk_b[1]["card_id"]} == {"brim-world-elite", "rbc-westjet-mc"}
    assert jaccard == 1.0


def test_find_disambiguation_candidates_gives_each_target_chunk_one_pair():
    # Reproduces the real duplicate: one clause shared by three cards produced
    # two pairs sharing a target chunk, and so two identical questions.
    shared_text = " ".join(f"word{i}" for i in range(40))
    chunks = [
        make_chunk("amex-platinum", "cardholder_agreement", shared_text),
        make_chunk("amex-gold-rewards", "cardholder_agreement", shared_text),
        make_chunk("amex-cobalt", "cardholder_agreement", shared_text),
    ]
    pairs = find_disambiguation_candidates(chunks, min_jaccard=0.6)
    targets = [pair[0][0] for pair in pairs]
    assert len(targets) == len(set(targets))


def test_find_disambiguation_candidates_excludes_same_card_pairs():
    shared_text = " ".join(f"word{i}" for i in range(40))
    chunks = [
        make_chunk("brim-world-elite", "insurance_certificate", shared_text, chunk_index=0),
        make_chunk("brim-world-elite", "insurance_certificate", shared_text, chunk_index=1),
    ]
    assert find_disambiguation_candidates(chunks, min_jaccard=0.6) == []


def _minimal_card(card_id: str, annual_fee_cad: float = 0.0) -> Card:
    return Card.model_validate(
        {
            "card_id": card_id,
            "name": card_id,
            "issuer": "Test Bank",
            "network": "Visa",
            "annual_fee_cad": annual_fee_cad,
            "rewards_summary": "n/a",
            "rewards_detail": {},
            "foreign_transaction_fee_pct": 2.5,
            "insurance_summary": "n/a",
            "insurance_detail": {},
            "best_for": [],
            "not_great_for": [],
            "official_url": "https://example.com",
            "last_verified": "2026-01-01",
        }
    )


def test_find_cross_source_candidates_only_returns_chunks_with_a_matching_card():
    chunks = [
        make_chunk("amex-cobalt", "cardholder_agreement", "The fee is $29."),
        make_chunk("unknown-card", "cardholder_agreement", "The fee is $10."),
    ]
    cards_by_id = {"amex-cobalt": _minimal_card("amex-cobalt")}
    found = find_cross_source_candidates(chunks, cards_by_id)
    assert [cid for cid, _meta, _facts, _card in found] == ["amex-cobalt::cardholder_agreement::0"]


def test_grounded_true_when_a_source_figure_appears_in_the_answer():
    assert _grounded(
        "The overlimit fee is $29.", "Section 3: the overlimit fee is $29 per statement."
    )


def test_grounded_false_when_the_answer_invents_a_different_figure():
    assert not _grounded(
        "The overlimit fee is $50.", "Section 3: the overlimit fee is $29 per statement."
    )


def test_grounded_true_when_source_has_no_numeric_fact_to_check():
    assert _grounded("This is excluded.", "This benefit does not cover pre-existing conditions.")


def test_build_unanswerable_returns_one_entry_per_spec():
    results = build_unanswerable({})
    assert len(results) == len(UNANSWERABLE_SPECS)
    assert all(r["question_type"] == "unanswerable" for r in results)
    assert all(r["answering_chunk_ids"] == [] for r in results)


def test_build_unanswerable_fails_loudly_if_its_absent_card_now_exists():
    fake_cards_by_id = {"amex-platinum-usd": _minimal_card("amex-platinum-usd")}
    with pytest.raises(AssertionError):
        build_unanswerable(fake_cards_by_id)


def test_shared_bigrams_catches_a_heading_echoed_back():
    source = "TRAVEL MEDICAL INSURANCE\nFor Covered Trips of 21 days or less."
    question = "How many days of travel medical insurance coverage do I get?"
    shared = _shared_bigrams(question, source, "Some Card")
    assert "travel medical" in shared
    assert "medical insurance" in shared


def test_shared_bigrams_empty_for_a_genuine_paraphrase():
    source = "TRAVEL MEDICAL INSURANCE\nFor Covered Trips of 21 days or less."
    question = "If I get sick on a short trip, how long am I protected for?"
    assert _shared_bigrams(question, source, "Some Card") == set()


def test_shared_bigrams_ignores_the_cards_own_name():
    source = "The Amex Cobalt Card overlimit fee is $29."
    question = "What is the Amex Cobalt Card overlimit fee?"
    # "overlimit fee" is a real echo; "amex cobalt" only repeats the
    # required card name and must not count against the question.
    shared = _shared_bigrams(question, source, "Amex Cobalt Card")
    assert "amex cobalt" not in shared
    assert "overlimit fee" in shared


def test_cross_source_grounded_requires_both_the_fee_and_the_chunk_figure():
    chunk_text = "The overlimit fee is $29 per statement."
    assert _cross_source_grounded(
        "Yes, the fee is $120.00 and the overlimit fee is $29.", 120.0, chunk_text
    )


def test_cross_source_grounded_false_when_fee_is_missing():
    chunk_text = "The overlimit fee is $29 per statement."
    assert not _cross_source_grounded("Yes, the overlimit fee is $29.", 120.0, chunk_text)


def test_cross_source_grounded_false_when_chunk_figure_is_missing():
    chunk_text = "The overlimit fee is $29 per statement."
    assert not _cross_source_grounded("Yes, the annual fee is $120.00.", 120.0, chunk_text)


def test_cross_source_grounded_false_when_answer_restates_an_invented_threshold():
    # An external review caught exactly this: the question's own made-up
    # comparison number ($150) leaking into ground_truth, which isn't a
    # figure either real source actually states.
    chunk_text = "Coverage is up to $5,000,000 per insured person, per trip."
    answer = "Yes, the fee is $120.00, which is under $150, and coverage is $5,000,000."
    assert not _cross_source_grounded(answer, 120.0, chunk_text)


def test_mentions_own_card_true_when_the_chunk_names_its_card():
    text = "Amex Cobalt Card, American Express Gold Rewards Card, Amex Green Card"
    assert _mentions_own_card(text, "American Express Gold Rewards Card")


def test_mentions_own_card_false_for_a_nameless_shared_clause():
    text = "You may make one claim in any twelve consecutive month period."
    assert not _mentions_own_card(text, "Brim World Elite Mastercard")


def test_mentions_own_card_ignores_trademark_symbols():
    text = "Your Amex Cobalt® Card benefits include..."
    assert _mentions_own_card(text, "Amex Cobalt Card")


def test_find_disambiguation_candidates_excludes_chunks_that_name_their_own_card():
    # Reproduces the real failure: a shared table-of-contents page names its
    # own card even though the surrounding wording is otherwise a
    # near-duplicate of another card's document.
    shared_body = " ".join(f"word{i}" for i in range(40))
    chunks = [
        make_chunk(
            "amex-gold-rewards",
            "cardholder_agreement",
            f"Table of contents for the Amex Gold Rewards Card agreement. {shared_body}",
            card_name="Amex Gold Rewards Card",
        ),
        make_chunk(
            "amex-platinum",
            "cardholder_agreement",
            f"Table of contents for the Amex Platinum agreement. {shared_body}",
            card_name="Amex Platinum",
        ),
    ]
    assert find_disambiguation_candidates(chunks, min_jaccard=0.6) == []


def test_complete_sentences_drops_the_unfinished_tail():
    text = "The fee is $150. It is charged yearly. The rebate applies if you"
    assert _complete_sentences(text) == "The fee is $150. It is charged yearly."


def test_complete_sentences_drops_a_leading_mid_sentence_fragment():
    text = "warranty up to two years. You must keep the receipt. Claims take 30 days."
    assert _complete_sentences(text) == "You must keep the receipt. Claims take 30 days."


def test_complete_sentences_leaves_a_whole_paragraph_alone():
    text = "The fee is $150.00 per year. It is not refundable."
    assert _complete_sentences(text) == text


def test_complete_sentences_returns_empty_when_no_sentence_finishes():
    assert _complete_sentences("still going with no end in sight") == ""


def test_complete_sentences_drops_the_cut_off_definition_from_the_real_failure():
    # The judged batch-3 failure: the chunk ends mid-definition ("...regulations in"),
    # and the drafted answer presented the unfinished definition as complete.
    text = (
        "4. Benefits Limited to Incurred Expenses. The total benefits paid to you cannot exceed "
        "the actual expenses which you have incurred. 5. Trade and Economic Sanctions. The "
        "Insurer shall not provide any coverage if doing so would breach any Prohibition. For "
        "the purposes of this Clause: Prohibition means any prohibition or restriction imposed "
        "by law or regulation including: b) any activities that would be subject to a license "
        "requirement under those laws and/ or regulations in"
    )
    trimmed = _complete_sentences(text)
    assert "Prohibition means" not in trimmed
    assert not trimmed.endswith("regulations in")


def _q(question: str, qtype: str, chunk_ids: list[str]) -> dict:
    return {
        "question": question,
        "ground_truth": "an answer",
        "question_type": qtype,
        "answering_chunk_ids": chunk_ids,
    }


def test_validate_questions_accepts_a_clean_set():
    from scripts.generate_hard_eval_questions import validate_questions

    qs = [_q("q one", "exact_term", ["a::0"]), _q("q two", "exact_term", ["b::0"])]
    assert validate_questions(qs, {"exact_term": 2}, {"a::0", "b::0"}) == []


def test_validate_questions_flags_a_short_category():
    from scripts.generate_hard_eval_questions import validate_questions

    qs = [_q("q one", "exact_term", ["a::0"])]
    problems = validate_questions(qs, {"exact_term": 2}, {"a::0"})
    assert problems == ["exact_term: 1 of 2"]


def test_validate_questions_flags_a_duplicate_question():
    from scripts.generate_hard_eval_questions import validate_questions

    qs = [_q("Same?", "exact_term", ["a::0"]), _q("same? ", "exact_term", ["b::0"])]
    problems = validate_questions(qs, {"exact_term": 2}, {"a::0", "b::0"})
    assert any("duplicate question" in p for p in problems)


def test_validate_questions_flags_a_chunk_backing_two_questions():
    from scripts.generate_hard_eval_questions import validate_questions

    qs = [_q("q one", "exact_term", ["a::0"]), _q("q two", "exclusion", ["a::0"])]
    problems = validate_questions(qs, {"exact_term": 1, "exclusion": 1}, {"a::0"})
    assert any("used by exact_term and exclusion" in p for p in problems)


def test_validate_questions_flags_a_chunk_id_not_in_the_corpus():
    from scripts.generate_hard_eval_questions import validate_questions

    qs = [_q("q one", "exact_term", ["ghost::0"])]
    problems = validate_questions(qs, {"exact_term": 1}, {"a::0"})
    assert any("unknown chunk id" in p for p in problems)


def test_builders_skip_claimed_chunks_and_claim_what_they_use(monkeypatch):
    import asyncio

    from scripts import generate_hard_eval_questions as gen

    async def fake_draft(card_name, chunk_text, style, doc_type="", feedback=None):
        return {"question": f"about {card_name}", "ground_truth": "The fee is $10."}

    monkeypatch.setattr(gen, "draft_question", fake_draft)
    chunks = [
        make_chunk("card-a", "cardholder_agreement", "The fee is $10 a year.", card_name="A"),
        make_chunk("card-b", "cardholder_agreement", "The fee is $10 a year.", card_name="B"),
    ]
    claimed = {"card-a::cardholder_agreement::0"}

    results = asyncio.run(gen.build_exact_term(chunks, 5, claimed))

    assert [r["answering_chunk_ids"] for r in results] == [["card-b::cardholder_agreement::0"]]
    assert claimed == {"card-a::cardholder_agreement::0", "card-b::cardholder_agreement::0"}


def test_a_spending_stop_keeps_the_questions_already_drafted(monkeypatch):
    # The real bug: the cap stopped the disambiguation loop at 20 of 30 and the
    # exception threw the 20 away, so the file said "0 of 30".
    import asyncio

    from scripts import generate_hard_eval_questions as gen
    from scripts.llm_cache import BudgetExceeded

    calls = 0

    async def fake_draft(card_name, chunk_text, style, doc_type="", feedback=None):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise BudgetExceeded("stopped at 1 paid calls")
        return {"question": f"about {card_name}", "ground_truth": "The fee is $10."}

    monkeypatch.setattr(gen, "draft_question", fake_draft)
    chunks = [
        make_chunk("card-a", "cardholder_agreement", "The fee is $10 a year.", card_name="A"),
        make_chunk("card-b", "cardholder_agreement", "The fee is $10 a year.", card_name="B"),
    ]
    collected: list[dict] = []

    with pytest.raises(BudgetExceeded):
        asyncio.run(gen.build_exact_term(chunks, 5, set(), collected))

    assert len(collected) == 1


def test_judge_fixes_patch_only_the_matching_question_type_and_chunk():
    from scripts.generate_hard_eval_questions import JUDGE_FIXES, apply_judge_fixes

    (qtype, cid), patch = next(iter(JUDGE_FIXES.items()))
    other_type = "exclusion" if qtype != "exclusion" else "exact_term"
    match = {"question_type": qtype, "answering_chunk_ids": [cid], "question": "old"}
    wrong_type = {"question_type": other_type, "answering_chunk_ids": [cid], "question": "old"}

    unused = apply_judge_fixes([match, wrong_type])

    assert wrong_type["question"] == "old"
    assert (match.get("question") or match.get("ground_truth")) in patch.values()
    assert (qtype, cid) not in unused
    assert len(unused) == len(JUDGE_FIXES) - 1


def test_every_rejected_chunk_has_a_reason():
    from scripts.generate_hard_eval_questions import REJECTED_CHUNKS

    assert REJECTED_CHUNKS and all(reason for reason in REJECTED_CHUNKS.values())
