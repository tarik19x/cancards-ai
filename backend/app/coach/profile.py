"""Building a credit profile from conversation, and deciding when it can be scored.

Readiness is decided by validating the partial CreditProfile against
ReadyCreditProfile. Pydantic's own missing-field errors drive the next question,
so adding a required field to the model is all it takes to make the coach start
asking for it -- the questions cannot drift out of step with the gate.
"""

import json
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from app.clients.anthropic_client import generate_answer
from app.logging_config import get_logger
from app.models import CreditProfile, ReadyCreditProfile

log = get_logger(__name__)

# Asked one at a time, in the order the frontend quiz uses. Asking for five facts
# in one breath reads like a form; the quiz established the one-at-a-time rhythm.
QUESTION_ORDER = [
    "card_count",
    "utilization",
    "history_length",
    "missed_payments",
    "recent_inquiries",
]

# Written for a general audience: short sentences, no credit-industry words, and each
# question is followed by a plain explanation and the kind of answer that is enough
# ("about 20%", "since 2019"). The bold line is the question; the second paragraph is
# the help. Keep the key phrases ("credit limit", "oldest credit card") -- tests and the
# scenario harness look for them.
FIELD_QUESTIONS = {
    "card_count": (
        "**How many credit cards do you have open right now?**\n\n"
        "Count every card, even ones you hardly ever use."
    ),
    "utilization": (
        "**How much of your credit limit do you usually use?**\n\n"
        "Your credit limit is the most your cards let you spend in total. Look at the "
        "balance on your monthly statement. For example, a $3,000 balance on a $10,000 "
        'limit is 30%. A rough guess is fine, like "about 20%".'
    ),
    "history_length": (
        "**How long ago did you open your oldest credit card?**\n\n"
        "That's the first card you ever got, even if you don't use it anymore. A rough "
        'answer is fine, like "about 5 years" or "since 2019".'
    ),
    "missed_payments": (
        "**In the last 2 years, have you paid a credit card bill late or missed a "
        "payment?**\n\n"
        "Even one late payment counts. Be honest, it helps me give you better advice. "
        'You can say "never", "once or twice", "a few times", or "often".'
    ),
    "recent_inquiries": (
        "**In the last 12 months, how many times did you apply for a new credit card or "
        "loan?**\n\n"
        "Every application leaves a small mark on your credit report, even if you were "
        'turned down. "None" is a perfectly good answer.'
    ),
}

EXTRACT_SYSTEM_PROMPT = """You read a conversation between a user and a credit coach and \
pull out five facts about the user's credit, plus two optional ones.

Return ONLY a JSON object, no markdown fence:
{
  "card_count": null,
  "utilization": null,
  "history_length": null,
  "missed_payments": null,
  "recent_inquiries": null,
  "typical_balance_cad": null,
  "total_credit_limit_cad": null,
  "annual_income_cad": null
}

Allowed values:
- card_count: a whole number (0 is valid).
- utilization: "under10", "10to30", "30to50", "50to75", "over75".
- history_length: "under1", "1to3", "3to7", "over7" (years since the oldest card opened).
- missed_payments: "never", "rarely" (once or twice), "sometimes" (a few times), "often".
- recent_inquiries: a whole number of applications in the last 12 months (0 is valid).

Rules:
- Use null for anything the user has not actually said. Never guess, and never fill a
  field from a question the coach asked but the user has not answered yet.
- Numbers, percentages and years that appear only in the COACH's messages are examples,
  not facts about the user. "For example, a $3,000 balance on a $10,000 limit is 30%" in
  a coach message says nothing about this user. Only the user's own words count.
- utilization is ONLY for when the user states a percentage ("about 20%") or describes it
  in words ("almost maxed out" is over75). Map a percentage to its band. A percentage that
  sits exactly on an edge: 10% is "10to30", 30% is "30to50", 50% is "50to75", and 75% is
  still "50to75" (only MORE than 75% is "over75").
- If the user gives a dollar amount instead, do NOT set utilization. Put a balance in
  typical_balance_cad and a limit in total_credit_limit_cad; the program works out the
  percentage itself. A bare number such as "800" or "$2,000" given right after the coach
  asked about their balance or limit is typical_balance_cad. If the coach asked for their
  limit and they reply with a number, that is total_credit_limit_cad. Use the coach's most
  recent question to tell which one it is.
- Work out history_length from a date or an age, using the current year given in the
  conversation header. A card opened in 2019, in a year 2026 conversation, is 7 years old.
  A number of years that sits exactly on an edge goes to the HIGHER band: 1 year is "1to3",
  3 years is "3to7", 7 years is "over7". "About two years" is "1to3".
- "No missed payments" means "never". "I think I was late once" means "rarely".
- Zero is a real answer for card_count and recent_inquiries. Return 0, not null.
- Keep anything already known unless the user corrects it."""


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    """Pull the JSON object out of a reply that may be wrapped in prose or a fence."""
    text = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def utilization_band(balance: float, limit: float) -> str:
    """The quiz's five bands for a balance against a limit.

    Edges follow the quiz's own labels: "Under 10%" excludes 10, "Over 75%" excludes 75, and
    "Under 30%" is the target for the 10-30 band. So exactly 10%, 30% and 50% move up a
    band, but exactly 75% stays in "50to75".
    """
    ratio = balance / limit
    if ratio < 0.10:
        return "under10"
    if ratio < 0.30:
        return "10to30"
    if ratio < 0.50:
        return "30to50"
    if ratio <= 0.75:
        return "50to75"
    return "over75"


def derive_utilization(profile: CreditProfile) -> CreditProfile:
    """Work the band out from dollars when the user gave a balance and a limit.

    Done here in code rather than left to the language model: it is arithmetic, and a
    model that is asked to do it will sometimes round to the wrong band.
    """
    limit = profile.total_credit_limit_cad
    balance = profile.typical_balance_cad
    if limit is None or balance is None or limit <= 0:
        return profile
    return profile.model_copy(update={"utilization": utilization_band(balance, limit)})


def missing_fields(profile: CreditProfile) -> list[str]:
    """Required facts the profile still lacks, in the order they are asked.

    Empty means the estimate can be computed.
    """
    try:
        ReadyCreditProfile.model_validate(profile.model_dump())
    except ValidationError as exc:
        missing = {str(err["loc"][0]) for err in exc.errors() if err["loc"]}
        return [f for f in QUESTION_ORDER if f in missing]
    return []


# Asked instead of the main question when the coach is half way through the balance
# question: it already has one of the two dollar amounts and only needs the other.
ASK_FOR_LIMIT = (
    "**Thanks. What's the total credit limit across your cards?**\n\n"
    "That's the most your cards let you spend in total. You can find it on your statements. "
    "A rough number is fine."
)
ASK_FOR_BALANCE = (
    "**Thanks. About how much do you usually owe on your statement?**\n\n"
    "Use the balance shown on your monthly statement. A rough number is fine."
)

# Used when the main question was just asked and the answer still did not fill the gap.
# Saying the same thing again is the worst response to someone who did not understand it,
# so this one admits the miss and offers an easier way to answer.
REPHRASED_QUESTIONS = {
    "card_count": (
        "**Sorry, I didn't catch that. How many credit cards do you have?**\n\n"
        'A number is all I need, like "2". If you have none, say "0".'
    ),
    "utilization": (
        "**Sorry, I couldn't work that out. Let's try it another way.**\n\n"
        "Roughly what percent of your credit limit do you use? Or tell me your usual "
        'balance and your total limit, like "$2,000 out of $10,000".'
    ),
    "history_length": (
        "**Sorry, I didn't catch that. About how many years ago did you open your first "
        "credit card?**\n\n"
        'A rough guess is fine, like "3 years" or "since 2018".'
    ),
    "missed_payments": (
        "**Sorry, I didn't catch that. Have you ever paid a credit card bill late in the "
        "last 2 years?**\n\n"
        'Just pick one: "never", "once or twice", "a few times", or "often".'
    ),
    "recent_inquiries": (
        "**Sorry, I didn't catch that. How many times did you apply for a card or loan in "
        "the last year?**\n\n"
        'A number is all I need, like "1". Say "0" if you did not apply for anything.'
    ),
}


def next_question(
    fields: list[str],
    profile: CreditProfile | None = None,
    previous_reply: str | None = None,
) -> str:
    """The single next thing to ask about.

    profile lets the balance question ask only for the dollar amount still missing.
    previous_reply is the coach's last message: if it is the exact question about to be
    asked, the user's answer did not help, so ask it a different way instead of again.
    """
    for field in QUESTION_ORDER:
        if field not in fields:
            continue
        if field == "utilization" and profile is not None:
            has_balance = profile.typical_balance_cad is not None
            has_limit = profile.total_credit_limit_cad is not None
            if has_balance and not has_limit:
                return (
                    ASK_FOR_LIMIT if previous_reply != ASK_FOR_LIMIT else REPHRASED_QUESTIONS[field]
                )
            if has_limit and not has_balance:
                return (
                    ASK_FOR_BALANCE
                    if previous_reply != ASK_FOR_BALANCE
                    else REPHRASED_QUESTIONS[field]
                )
        question = FIELD_QUESTIONS[field]
        return REPHRASED_QUESTIONS[field] if previous_reply == question else question
    return "Is there anything else you would like to tell me about your credit?"


def merge_profile(known: CreditProfile, update: dict[str, Any]) -> CreditProfile:
    """Fold an extraction result into what is already known.

    A null from the extractor means "not mentioned this turn", never "forget it" --
    without this, turn 4 would wipe what the user said on turn 1. Zero is a real
    answer for card counts and inquiries, so the check is `is None`, not falsiness.
    """
    merged = known.model_dump()
    for key, value in update.items():
        if value is not None and key in merged:
            merged[key] = value
    try:
        merged_profile = CreditProfile.model_validate(merged)
    except ValidationError as exc:
        # A bad band or a negative count must not crash the turn: keep what was
        # already valid and let the coach ask again.
        log.warning("profile_update_rejected", error=str(exc))
        return known
    # A percentage the user stated this turn wins; otherwise dollars are turned into a
    # band, and re-derived if the user later corrects either number.
    if update.get("utilization") is None:
        merged_profile = derive_utilization(merged_profile)
    return merged_profile


def _current_year() -> int:
    """Its own function so the replay gate can pin the year its recording was made in;
    otherwise every recorded prompt would stop matching on 1 January."""
    return datetime.now(UTC).year


# Added only once an estimate exists. Follow-up questions are full of "what if" and "should
# I", and without this a hypothetical balance would overwrite the real one and re-score.
AFTER_SCORE_NOTE = (
    "The user already has an estimate and is asking follow-up questions. Only change a fact "
    "if they say it was wrong or has really changed. A 'what if', a plan or a question "
    "('what if I paid it down to $500', 'should I close a card') is NOT a fact: return null."
)


async def extract_profile(
    messages: list[dict[str, str]], known: CreditProfile, after_score: bool = False
) -> CreditProfile:
    """Update the profile from the conversation so far. One LLM call per turn."""
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    # The model has no clock. Without this, "my first card was from 2019" is only right by
    # luck, and silently goes stale every January.
    user_prompt = (
        f"The current year is {_current_year()}.\n\n"
        f"Already known:\n{known.model_dump_json()}\n\nConversation:\n{transcript}\n\n"
        "Return the updated JSON object."
    )
    if after_score:
        user_prompt = f"{AFTER_SCORE_NOTE}\n\n{user_prompt}"
    raw = await generate_answer(EXTRACT_SYSTEM_PROMPT, user_prompt, max_tokens=400)
    parsed = _parse_json_object(raw)
    if parsed is None:
        # The model sometimes reasons out loud instead of answering, and a corrections turn
        # ("actually it's $1,000") is where it does it most. Dropping that turn would leave
        # the old, wrong fact in place, so ask once more, bluntly, before giving up.
        log.warning("profile_extraction_unparsed", raw=raw[:200])
        raw = await generate_answer(
            EXTRACT_SYSTEM_PROMPT,
            user_prompt + "\n\nReply with the JSON object only. Start with { and no other text.",
            max_tokens=400,
        )
        parsed = _parse_json_object(raw)
        if parsed is None:
            log.warning("profile_extraction_gave_up", raw=raw[:200])
            return known
    return merge_profile(known, parsed)
