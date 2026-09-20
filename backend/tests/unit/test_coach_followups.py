"""The coach must never ask the same question twice in a row.

Regression for a bug found by using the chat: a user answered the balance question with a
bare "800", the coach could not turn a dollar amount into a percentage, and repeated the
identical question on every following turn.
"""

import pytest

from app.coach.profile import (
    ASK_FOR_BALANCE,
    ASK_FOR_LIMIT,
    FIELD_QUESTIONS,
    QUESTION_ORDER,
    REPHRASED_QUESTIONS,
    derive_utilization,
    merge_profile,
    missing_fields,
    next_question,
    utilization_band,
)
from app.models import CreditProfile


@pytest.mark.parametrize(
    ("balance", "limit", "band"),
    [
        (500, 10_000, "under10"),  # 5%
        (999, 10_000, "under10"),  # just under 10%
        (1_000, 10_000, "10to30"),  # exactly 10% is the next band up
        (2_999, 10_000, "10to30"),
        (3_000, 10_000, "30to50"),  # exactly 30%: "under 30%" no longer applies
        (4_999, 10_000, "30to50"),
        (5_000, 10_000, "50to75"),
        (7_499, 10_000, "50to75"),
        (7_500, 10_000, "50to75"),  # exactly 75%: the quiz says "over 75%"
        (7_501, 10_000, "over75"),
        (12_000, 10_000, "over75"),  # over the limit is still the top band
        (0, 10_000, "under10"),  # pays it all off: a valid, excellent answer
    ],
)
def test_the_band_is_worked_out_from_dollars(balance, limit, band):
    assert utilization_band(balance, limit) == band


def test_a_balance_alone_does_not_invent_a_band():
    profile = derive_utilization(CreditProfile(typical_balance_cad=800))
    assert profile.utilization is None


def test_a_balance_and_a_limit_together_fill_in_the_band():
    profile = derive_utilization(
        CreditProfile(typical_balance_cad=800, total_credit_limit_cad=2_000)
    )
    assert profile.utilization == "30to50"  # 40%


def test_a_zero_limit_is_ignored_rather_than_dividing_by_zero():
    profile = derive_utilization(CreditProfile(typical_balance_cad=800, total_credit_limit_cad=0))
    assert profile.utilization is None


def test_the_user_from_the_bug_report_now_gets_a_band():
    # "800" then "2000", exactly as typed in the chat that repeated itself.
    profile = merge_profile(CreditProfile(card_count=3), {"typical_balance_cad": 800})
    assert "utilization" in missing_fields(profile)
    profile = merge_profile(profile, {"total_credit_limit_cad": 2000})
    assert profile.utilization == "30to50"
    assert "utilization" not in missing_fields(profile)


def test_a_percentage_the_user_states_wins_over_dollars():
    known = CreditProfile(typical_balance_cad=800, total_credit_limit_cad=2_000)
    merged = merge_profile(known, {"utilization": "under10"})
    assert merged.utilization == "under10"


def test_a_corrected_balance_recomputes_the_band():
    known = merge_profile(
        CreditProfile(), {"typical_balance_cad": 800, "total_credit_limit_cad": 10_000}
    )
    assert known.utilization == "under10"
    assert merge_profile(known, {"typical_balance_cad": 6_000}).utilization == "50to75"


def test_with_only_a_balance_the_coach_asks_for_the_limit_not_the_same_question():
    profile = CreditProfile(card_count=3, typical_balance_cad=800)
    question = next_question(missing_fields(profile), profile)
    assert question == ASK_FOR_LIMIT
    assert question != FIELD_QUESTIONS["utilization"]


def test_with_only_a_limit_the_coach_asks_for_the_balance():
    profile = CreditProfile(card_count=3, total_credit_limit_cad=10_000)
    assert next_question(missing_fields(profile), profile) == ASK_FOR_BALANCE


@pytest.mark.parametrize("field", QUESTION_ORDER)
def test_a_question_that_was_just_asked_is_rephrased_never_repeated(field):
    profile = CreditProfile()
    # Make `field` the earliest missing one by filling everything before it.
    fills = {
        "card_count": 2,
        "utilization": "10to30",
        "history_length": "3to7",
        "missed_payments": "never",
        "recent_inquiries": 0,
    }
    known = {f: fills[f] for f in QUESTION_ORDER[: QUESTION_ORDER.index(field)]}
    profile = CreditProfile(**known)

    first = next_question(missing_fields(profile), profile, previous_reply=None)
    again = next_question(missing_fields(profile), profile, previous_reply=first)

    assert first == FIELD_QUESTIONS[field]
    assert again == REPHRASED_QUESTIONS[field]
    assert again != first


def test_asking_for_the_limit_twice_falls_back_to_the_easier_percentage_question():
    profile = CreditProfile(card_count=3, typical_balance_cad=800)
    again = next_question(missing_fields(profile), profile, previous_reply=ASK_FOR_LIMIT)
    assert again == REPHRASED_QUESTIONS["utilization"]
    assert "percent" in again


def test_every_question_has_a_rephrased_version_that_admits_the_miss():
    assert set(REPHRASED_QUESTIONS) == set(QUESTION_ORDER)
    for field, text in REPHRASED_QUESTIONS.items():
        assert text.startswith("**Sorry"), field
        assert text != FIELD_QUESTIONS[field]
