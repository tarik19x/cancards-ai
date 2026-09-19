"""The Credit Coach agent: a LangGraph state machine over the quiz's scoring model.

    extract_profile -> decide_ready -> ask_for_missing               (facts missing)
                                    -> score -> explain              (all five known)

The division of labour is the point. The language model reads the conversation and
pulls out five facts, and later puts the result into words. The number itself comes
from app/coach/scoring.py, which is deterministic: the score cannot drift between
identical runs, cannot be argued upward by a persistent user, and matches what the
frontend quiz shows for the same answers.

decide_ready can be switched off (settings.profile_validation). With it off the graph
routes straight to scoring, and scoring with facts missing falls through to a language
model guess -- which is exactly the naive behaviour the premature-advice rate measures.
"""

import operator
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from app.clients.anthropic_client import generate_answer
from app.coach.profile import extract_profile, missing_fields, next_question
from app.coach.scoring import score_credit
from app.config import get_settings
from app.logging_config import get_logger
from app.models import CreditProfile

log = get_logger(__name__)

EXPLAIN_SYSTEM_PROMPT = """You are a credit coach explaining an estimate someone just \
received. You will be given the total out of 100, the band, and each factor with its \
score and a line of advice.

Write a short, warm explanation in markdown:
- Open with the total and the band in one sentence.
- Name the one or two weakest factors and what to do about them, using the advice given.
- Close with one sentence of encouragement.

Rules:
- Use ONLY the numbers you are given. Never invent or adjust a score.
- Never call this a real credit score. It is an estimate from self-reported answers;
  a real score comes from Equifax or TransUnion.
- Keep it under 180 words. No headings."""

GUESS_SYSTEM_PROMPT = """You are a credit coach. The user has asked about their credit \
but has not given you all the facts needed to estimate it.

Answer their question as best you can from what they have said, in under 150 words of \
markdown. Never call this a real credit score."""


class CoachState(TypedDict, total=False):
    """operator.add makes each node's messages append rather than replace, which is
    also what the checkpointer replays when a thread resumes."""

    messages: Annotated[list[dict[str, str]], operator.add]
    profile: dict[str, Any]
    missing_fields: list[str]
    score: dict[str, Any] | None
    reply_markdown: str
    gave_score: bool
    turn_count: int


def _profile_of(state: CoachState) -> CreditProfile:
    return CreditProfile.model_validate(state.get("profile") or {})


def _transcript(state: CoachState) -> str:
    return "\n".join(f"{m['role']}: {m['content']}" for m in state.get("messages", []))


async def extract_profile_node(state: CoachState) -> CoachState:
    updated = await extract_profile(state.get("messages", []), _profile_of(state))
    return {"profile": updated.model_dump(), "turn_count": state.get("turn_count", 0) + 1}


async def decide_ready_node(state: CoachState) -> CoachState:
    if not get_settings().profile_validation:
        # The "before" configuration: never hold the score back. Kept as a switch
        # rather than a deleted branch so the two rates are measured on one codebase.
        return {"missing_fields": []}
    missing = missing_fields(_profile_of(state))
    log.info("readiness_checked", missing=missing, turn=state.get("turn_count", 0))
    return {"missing_fields": missing}


async def ask_for_missing_node(state: CoachState) -> CoachState:
    reply = next_question(state.get("missing_fields", []))
    return {
        "messages": [{"role": "assistant", "content": reply}],
        "reply_markdown": reply,
        "gave_score": False,
        "score": None,
    }


async def score_node(state: CoachState) -> CoachState:
    """Compute the estimate when the facts are all there.

    Recomputes what is missing rather than trusting decide_ready's output: that
    output depends on the toggle, but whether the facts are actually present does
    not. A None score here means the next node has to guess, which is the case the
    premature-advice rate counts.
    """
    profile = _profile_of(state)
    if missing_fields(profile):
        log.info("scoring_without_full_profile", missing=missing_fields(profile))
        return {"score": None}
    result = score_credit(
        card_count=profile.card_count,  # type: ignore[arg-type]
        utilization=profile.utilization,  # type: ignore[arg-type]
        history_length=profile.history_length,  # type: ignore[arg-type]
        missed_payments=profile.missed_payments,  # type: ignore[arg-type]
        recent_inquiries=profile.recent_inquiries,  # type: ignore[arg-type]
    )
    return {"score": result.model_dump()}


async def explain_node(state: CoachState) -> CoachState:
    score = state.get("score")
    if score is None:
        reply = await generate_answer(GUESS_SYSTEM_PROMPT, _transcript(state), max_tokens=400)
    else:
        factors = "\n".join(
            f"- {f['label']}: {f['score']}/{f['max']}. {f['advice']}" for f in score["factors"]
        )
        user_prompt = (
            f"Total: {score['total']}/100 ({score['band']})\nFactors, weakest first:\n{factors}"
        )
        reply = await generate_answer(EXPLAIN_SYSTEM_PROMPT, user_prompt, max_tokens=600)
    return {
        "messages": [{"role": "assistant", "content": reply}],
        "reply_markdown": reply,
        "gave_score": True,
    }


def route_on_readiness(state: CoachState) -> Literal["ask_for_missing", "score"]:
    return "ask_for_missing" if state.get("missing_fields") else "score"


def build_graph(checkpointer: Any = None) -> Any:
    """Compile the graph. Without a checkpointer it runs but forgets everything
    between turns, so the API always passes one.
    """
    builder = StateGraph(CoachState)
    builder.add_node("extract_profile", extract_profile_node)
    builder.add_node("decide_ready", decide_ready_node)
    builder.add_node("ask_for_missing", ask_for_missing_node)
    builder.add_node("score", score_node)
    builder.add_node("explain", explain_node)

    builder.add_edge(START, "extract_profile")
    builder.add_edge("extract_profile", "decide_ready")
    builder.add_conditional_edges(
        "decide_ready",
        route_on_readiness,
        {"ask_for_missing": "ask_for_missing", "score": "score"},
    )
    builder.add_edge("ask_for_missing", END)
    builder.add_edge("score", "explain")
    builder.add_edge("explain", END)
    return builder.compile(checkpointer=checkpointer)
