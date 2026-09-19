"""Credit health estimate — a direct port of frontend/src/lib/credit-score.ts.

Self-reported estimate only, never a real bureau score: a real score comes from
Equifax/TransUnion pulling actual account history, and nothing typed into a form
can reproduce that honestly. The weights loosely mirror the public FICO factor
breakdown (payment history ~35%, utilization ~30%, history length ~15%, new
credit ~10%, mix ~10%) for educational shape, not precision.

Deliberately deterministic and LLM-free. The agent's language model extracts the
five facts from the conversation and later explains the result, but the number
itself is computed here -- so the score cannot drift between runs, cannot be
argued up by a persistent user, and is identical to what the frontend quiz shows.

Kept in step with the TypeScript version by hand. The two are tested against a
shared table of cases (tests/unit/test_coach_scoring.py); if the weights change,
both move together or the test fails.
"""

from typing import Literal

from pydantic import BaseModel

Utilization = Literal["under10", "10to30", "30to50", "50to75", "over75"]
HistoryLength = Literal["under1", "1to3", "3to7", "over7"]
MissedPayments = Literal["never", "rarely", "sometimes", "often"]


class Factor(BaseModel):
    key: str
    label: str
    score: int
    max: int
    advice: str


class ScoreResult(BaseModel):
    total: int  # 0-100
    band: Literal["Needs work", "Fair", "Good", "Very good", "Excellent"]
    factors: list[Factor]  # weakest first -- that is the order advice should be read in


_UTILIZATION: dict[str, tuple[int, str]] = {
    "under10": (30, "Utilization is already low - this isn't costing you anything."),
    "10to30": (24, "Under 30% is the usual target. Pushing toward 10% would help further."),
    "30to50": (15, "Balances above 30% of your limit start pulling the score down noticeably."),
    "50to75": (
        7,
        "This is a heavy load on your limit. Paying it down is the single fastest lever you have.",
    ),
    "over75": (2, "Running this close to the limit is the biggest thing hurting you right now."),
}

_HISTORY: dict[str, tuple[int, str]] = {
    "under1": (
        3,
        "History is still short - this improves on its own with time, nothing to actively fix.",
    ),
    "1to3": (7, "Still building. Keep your oldest card open even if you stop using it."),
    "3to7": (
        11,
        "Solid length. Avoid closing your oldest account - that's the one doing the most work.",
    ),
    "over7": (15, "Long history is working in your favour here."),
}

_MISSED: dict[str, tuple[int, str]] = {
    "never": (
        35,
        "A clean payment record is the single heaviest factor - this is your strongest area.",
    ),
    "rarely": (
        22,
        "One or two slips are recoverable, but even occasional late payments carry real weight.",
    ),
    "sometimes": (
        10,
        "This is likely the main thing holding the score back. Autopay for at least the "
        "minimum removes the risk entirely.",
    ),
    "often": (
        0,
        "This is the top priority. Everything else matters less until payments are "
        "consistently on time.",
    ),
}

_INQUIRIES: dict[int, tuple[int, str]] = {
    0: (10, "No recent applications - nothing dragging you down here."),
    1: (7, "One inquiry is minor and fades within a year."),
    2: (4, "A couple of recent applications add up. Space out any future ones."),
    3: (
        0,
        "Several applications in a short window reads as risk to lenders. Hold off on new "
        "applications for a while.",
    ),
}


def _score_mix(card_count: int) -> Factor:
    if card_count == 0:
        score, advice = (
            2,
            (
                "No open cards means no history being built. A single no-fee card is the "
                "easiest starting point."
            ),
        )
    elif card_count == 1:
        score, advice = (
            6,
            ("One card works, but a second with a different limit gives lenders more to evaluate."),
        )
    elif card_count <= 4:
        score, advice = 10, "This is a healthy range - nothing to change here."
    elif card_count == 5:
        score, advice = 7, "Getting a little wide. Not harmful, just more to manage."
    else:
        score, advice = (
            4,
            (
                "This many open cards can look like risk, even with good management. Consider "
                "whether all of them are still earning their keep."
            ),
        )
    return Factor(key="mix", label="Number of cards", score=score, max=10, advice=advice)


def band_for(total: int) -> str:
    if total >= 90:
        return "Excellent"
    if total >= 75:
        return "Very good"
    if total >= 60:
        return "Good"
    if total >= 40:
        return "Fair"
    return "Needs work"


def score_credit(
    *,
    card_count: int,
    utilization: Utilization,
    history_length: HistoryLength,
    missed_payments: MissedPayments,
    recent_inquiries: int,
) -> ScoreResult:
    """The five factors, their total, and the advice order.

    recent_inquiries is clamped rather than rejected: "three or more" is the last
    band the quiz offers, so a user who says five is asking about the same bucket.
    """
    inquiries = min(max(recent_inquiries, 0), 3)
    missed_score, missed_advice = _MISSED[missed_payments]
    util_score, util_advice = _UTILIZATION[utilization]
    history_score, history_advice = _HISTORY[history_length]
    inquiry_score, inquiry_advice = _INQUIRIES[inquiries]

    factors = [
        Factor(
            key="payments",
            label="Payment history",
            score=missed_score,
            max=35,
            advice=missed_advice,
        ),
        Factor(
            key="utilization",
            label="Credit utilization",
            score=util_score,
            max=30,
            advice=util_advice,
        ),
        Factor(
            key="history",
            label="Length of credit history",
            score=history_score,
            max=15,
            advice=history_advice,
        ),
        Factor(
            key="inquiries",
            label="Recent applications",
            score=inquiry_score,
            max=10,
            advice=inquiry_advice,
        ),
        _score_mix(card_count),
    ]

    total = sum(f.score for f in factors)
    factors.sort(key=lambda f: f.score / f.max)
    return ScoreResult(total=total, band=band_for(total), factors=factors)  # type: ignore[arg-type]
