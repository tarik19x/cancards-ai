"""The Python scorer must agree with frontend/src/lib/credit-score.ts.

Expected totals below were computed by hand from the TypeScript weight tables,
not from this module's own output -- a test that only asserts what the code
already does would pass even if the port were wrong.
"""

import pytest

from app.coach.scoring import band_for, score_credit

PERFECT = {
    "card_count": 3,
    "utilization": "under10",
    "history_length": "over7",
    "missed_payments": "never",
    "recent_inquiries": 0,
}
WORST = {
    "card_count": 0,
    "utilization": "over75",
    "history_length": "under1",
    "missed_payments": "often",
    "recent_inquiries": 3,
}


def test_the_best_possible_answers_score_100():
    # 35 payments + 30 utilization + 15 history + 10 inquiries + 10 mix
    result = score_credit(**PERFECT)
    assert result.total == 100
    assert result.band == "Excellent"


def test_the_worst_possible_answers_score_7():
    # 0 payments + 2 utilization + 3 history + 0 inquiries + 2 mix
    result = score_credit(**WORST)
    assert result.total == 7
    assert result.band == "Needs work"


def test_a_typical_middle_profile():
    # 22 rarely + 15 (30-50%) + 7 (1-3 yrs) + 7 (one inquiry) + 10 (3 cards) = 61
    result = score_credit(
        card_count=3,
        utilization="30to50",
        history_length="1to3",
        missed_payments="rarely",
        recent_inquiries=1,
    )
    assert result.total == 61
    assert result.band == "Good"


@pytest.mark.parametrize(
    ("total", "band"),
    [(100, "Excellent"), (90, "Excellent"), (89, "Very good"), (75, "Very good"),
     (74, "Good"), (60, "Good"), (59, "Fair"), (40, "Fair"), (39, "Needs work"), (0, "Needs work")],
)  # fmt: skip
def test_band_boundaries_match_the_frontend(total, band):
    assert band_for(total) == band


@pytest.mark.parametrize(
    ("cards", "expected"), [(0, 2), (1, 6), (2, 10), (4, 10), (5, 7), (6, 4), (12, 4)]
)
def test_card_mix_thresholds_match_the_frontend(cards, expected):
    result = score_credit(**{**PERFECT, "card_count": cards})
    mix = next(f for f in result.factors if f.key == "mix")
    assert mix.score == expected


def test_factors_come_back_weakest_first_because_that_is_the_advice_order():
    result = score_credit(
        card_count=3,
        utilization="under10",  # 30/30 = strongest
        history_length="under1",  # 3/15 = weakest
        missed_payments="never",
        recent_inquiries=0,
    )
    ratios = [f.score / f.max for f in result.factors]
    assert ratios == sorted(ratios)
    assert result.factors[0].key == "history"


def test_every_factor_carries_advice_the_explanation_can_quote():
    for factor in score_credit(**WORST).factors:
        assert factor.advice.strip()


def test_more_inquiries_than_the_quiz_offers_land_in_the_top_band():
    # "Three or more" is the last option, so 7 applications is the same bucket as 3.
    assert (
        score_credit(**{**PERFECT, "recent_inquiries": 7}).total
        == score_credit(**{**PERFECT, "recent_inquiries": 3}).total
    )
