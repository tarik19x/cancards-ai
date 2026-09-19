"""Readiness and profile-merge rules -- pure logic, no LLM calls."""

from app.coach.profile import (
    FIELD_QUESTIONS,
    QUESTION_ORDER,
    merge_profile,
    missing_fields,
    next_question,
)
from app.models import CreditProfile

COMPLETE = {
    "card_count": 3,
    "utilization": "10to30",
    "history_length": "3to7",
    "missed_payments": "never",
    "recent_inquiries": 1,
}


def test_an_empty_profile_is_missing_every_scoring_field():
    assert missing_fields(CreditProfile()) == QUESTION_ORDER


def test_a_complete_profile_is_ready():
    assert missing_fields(CreditProfile(**COMPLETE)) == []


def test_zero_cards_and_zero_inquiries_count_as_answered():
    # The trap: both are valid answers and both are falsy. A truthiness check here
    # would ask a user with no cards for their card count forever.
    profile = CreditProfile(**{**COMPLETE, "card_count": 0, "recent_inquiries": 0})
    assert missing_fields(profile) == []


def test_context_fields_are_never_required():
    # Income and limit are collected for eligibility, not scoring, so their absence
    # must never hold up the estimate.
    profile = CreditProfile(**COMPLETE)
    assert profile.annual_income_cad is None and profile.total_credit_limit_cad is None
    assert missing_fields(profile) == []


def test_missing_fields_come_back_in_the_order_they_are_asked():
    profile = CreditProfile(missed_payments="never", card_count=2)
    assert missing_fields(profile) == ["utilization", "history_length", "recent_inquiries"]


def test_only_one_question_is_asked_at_a_time_and_it_is_the_earliest_missing():
    question = next_question(["recent_inquiries", "utilization"])
    assert "credit limit" in question
    assert "apply" not in question


def test_a_null_from_the_extractor_does_not_wipe_what_is_known():
    known = CreditProfile(card_count=3, utilization="10to30")
    merged = merge_profile(known, {"card_count": None, "history_length": "over7"})
    assert merged.card_count == 3
    assert merged.utilization == "10to30"
    assert merged.history_length == "over7"


def test_a_user_correction_overwrites_the_old_value():
    known = CreditProfile(card_count=3)
    assert merge_profile(known, {"card_count": 5}).card_count == 5


def test_a_zero_from_the_extractor_is_stored_not_treated_as_absent():
    known = CreditProfile(card_count=3)
    assert merge_profile(known, {"card_count": 0}).card_count == 0


def test_an_invalid_value_from_the_model_is_rejected_without_losing_the_profile():
    known = CreditProfile(**COMPLETE)
    merged = merge_profile(known, {"utilization": "quite a lot", "card_count": 4})
    # The whole update is dropped rather than half-applied, so the profile stays coherent.
    assert merged == known


def test_a_negative_count_is_rejected():
    known = CreditProfile(card_count=2)
    assert merge_profile(known, {"recent_inquiries": -1}) == known


def test_unknown_keys_from_the_model_are_ignored():
    known = CreditProfile(card_count=2)
    assert merge_profile(known, {"credit_score": 780}).card_count == 2


# Words a general audience should not meet in a question. "Utilization" is the scorer's
# internal name for the balance question; the user never needs to see it.
JARGON = ["utilization", "hard inquiry", "inquiries", "revolving", "tradeline", "derogatory"]


def test_every_field_has_a_question_and_they_follow_the_asking_order():
    assert list(FIELD_QUESTIONS) == QUESTION_ORDER


def test_questions_use_plain_words_and_explain_themselves():
    for field, text in FIELD_QUESTIONS.items():
        assert not any(word in text.lower() for word in JARGON), f"{field} uses jargon"
        # A bold question, then a separate paragraph of help.
        question, _, help_text = text.partition("\n\n")
        assert question.startswith("**") and question.endswith("**"), field
        assert len(help_text) > 20, f"{field} has no explanation"


def test_questions_stay_short_enough_to_read_at_a_glance():
    for field, text in FIELD_QUESTIONS.items():
        assert len(text) < 400, f"{field} is {len(text)} characters"


async def test_the_extractor_is_told_the_current_year(monkeypatch):
    # "since 2019" means nothing to a model that does not know what year it is.
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock

    from app.coach import profile as profile_module

    seen = AsyncMock(return_value="{}")
    monkeypatch.setattr(profile_module, "generate_answer", seen)

    await profile_module.extract_profile(
        [{"role": "user", "content": "my first card was from 2019"}], CreditProfile()
    )

    prompt = seen.call_args.args[1]
    assert f"The current year is {datetime.now(UTC).year}." in prompt


async def test_a_prose_reply_from_the_extractor_gets_one_retry(monkeypatch):
    # A correction turn is where the model most often explains instead of answering. Losing
    # that turn would keep the old wrong fact, so the second, blunter ask must be used.
    from unittest.mock import AsyncMock

    from app.coach import profile as profile_module

    seen = AsyncMock(side_effect=["Let me think about that first...", '{"card_count": 4}'])
    monkeypatch.setattr(profile_module, "generate_answer", seen)

    result = await profile_module.extract_profile(
        [{"role": "user", "content": "4 cards"}], CreditProfile()
    )

    assert result.card_count == 4
    assert seen.await_count == 2
    assert "JSON object only" in seen.call_args.args[1]


async def test_two_prose_replies_in_a_row_keep_what_was_known(monkeypatch):
    from unittest.mock import AsyncMock

    from app.coach import profile as profile_module

    seen = AsyncMock(return_value="I cannot say.")
    monkeypatch.setattr(profile_module, "generate_answer", seen)
    known = CreditProfile(card_count=2)

    result = await profile_module.extract_profile([{"role": "user", "content": "hm"}], known)

    assert result == known
    assert seen.await_count == 2
