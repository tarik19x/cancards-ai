"""Building a credit profile from conversation, and deciding when it can be scored.

Readiness is decided by validating the partial CreditProfile against
ReadyCreditProfile. Pydantic's own missing-field errors drive the next question,
so adding a required field to the model is all it takes to make the coach start
asking for it -- the questions cannot drift out of step with the gate.
"""

import json
import re
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

FIELD_QUESTIONS = {
    "card_count": (
        "How many credit cards do you currently have open? Include cards you rarely use."
    ),
    "utilization": (
        "How much of your available credit do you typically carry? Compare your usual "
        "balance to your total limit, not what you pay off each month."
    ),
    "history_length": (
        "How long have you had your oldest credit card? The account you opened first, "
        "even if you barely use it now."
    ),
    "missed_payments": (
        "In the last two years, have you missed a payment? Even one counts, and being "
        "honest here is the whole point."
    ),
    "recent_inquiries": (
        "How many new cards or loans have you applied for in the last 12 months? Each "
        "application shows up as a hard inquiry on your file."
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
- Work out utilization if the user gives a balance and a limit: $2,000 on a $10,000
  limit is 20%, so "10to30". A bare percentage maps to its band the same way.
- Work out history_length from a date or an age: "since 2019" with a current year of
  2026 is "over7"; "about two years" is "1to3".
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


def next_question(fields: list[str]) -> str:
    """The single next thing to ask about."""
    for field in QUESTION_ORDER:
        if field in fields:
            return FIELD_QUESTIONS[field]
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
        return CreditProfile.model_validate(merged)
    except ValidationError as exc:
        # A bad band or a negative count must not crash the turn: keep what was
        # already valid and let the coach ask again.
        log.warning("profile_update_rejected", error=str(exc))
        return known


async def extract_profile(messages: list[dict[str, str]], known: CreditProfile) -> CreditProfile:
    """Update the profile from the conversation so far. One LLM call per turn."""
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    user_prompt = (
        f"Already known:\n{known.model_dump_json()}\n\nConversation:\n{transcript}\n\n"
        "Return the updated JSON object."
    )
    raw = await generate_answer(EXTRACT_SYSTEM_PROMPT, user_prompt, max_tokens=400)
    parsed = _parse_json_object(raw)
    if parsed is None:
        log.warning("profile_extraction_unparsed", raw=raw[:200])
        return known
    return merge_profile(known, parsed)
