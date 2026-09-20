"""What the coach does after the score: answer follow-up questions from the history.

Same stubbing as test_coach_graph.py: the extractor and the language model are fakes, so
these pin the routing and what the follow-up answer is given, not its wording.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.coach.graph import build_graph
from app.coach.scoring import score_credit, what_if_totals
from app.models import CreditProfile

COMPLETE = CreditProfile(
    card_count=3,
    utilization="30to50",
    history_length="3to7",
    missed_payments="never",
    recent_inquiries=1,
)
FACTS = {
    "card_count": 3,
    "utilization": "30to50",
    "history_length": "3to7",
    "missed_payments": "never",
    "recent_inquiries": 1,
}


@pytest.fixture(autouse=True)
def validation_on(monkeypatch):
    monkeypatch.setattr(
        "app.coach.graph.get_settings", lambda: SimpleNamespace(profile_validation=True)
    )


class Chat:
    """One conversation on one thread, with the extractor's next answer set per turn."""

    def __init__(self):
        self.graph = build_graph(InMemorySaver())
        self.config = {"configurable": {"thread_id": "t"}}
        self.extract = AsyncMock(return_value=COMPLETE)
        self.answer = AsyncMock(return_value="a reply")

    def say(self, text: str, profile: CreditProfile | None = None):
        if profile is not None:
            self.extract.return_value = profile
        with (
            patch("app.coach.graph.extract_profile", self.extract),
            patch("app.coach.graph.generate_answer", self.answer),
        ):
            return asyncio.run(
                self.graph.ainvoke({"messages": [{"role": "user", "content": text}]}, self.config)
            )


def test_a_message_after_the_score_is_a_follow_up_not_a_second_score():
    chat = Chat()
    first = chat.say("here are all my answers")
    second = chat.say("how do I raise it?")

    assert first["gave_score"] is True
    assert second["gave_score"] is False
    assert len(second["messages"]) == 4
    # The estimate is untouched by a question.
    assert second["score"] == first["score"]


def test_the_follow_up_is_given_the_facts_the_score_and_the_computed_what_ifs():
    chat = Chat()
    chat.say("all my answers")
    chat.say("what if I paid my balance down?")

    system, prompt = chat.answer.call_args.args[:2]
    assert "Never invent" in system
    assert '"card_count":3' in prompt
    assert "Estimate:" in prompt
    # Real totals from the scorer: 30to50 -> under10 is worth +15 here.
    assert "Keeping the balance under 10% of the credit limit: total would be" in prompt
    assert "what if I paid my balance down?" in prompt


def test_the_extractor_is_told_a_score_exists_only_after_one_does():
    chat = Chat()
    chat.say("all my answers")
    assert chat.extract.call_args.kwargs["after_score"] is False
    chat.say("what if I paid it off?")
    assert chat.extract.call_args.kwargs["after_score"] is True


def test_a_real_correction_after_the_score_gives_a_new_score():
    chat = Chat()
    first = chat.say("all my answers")
    corrected = COMPLETE.model_copy(update={"utilization": "under10"})
    second = chat.say("actually my balance is tiny", corrected)

    assert second["gave_score"] is True
    assert second["score"]["total"] > first["score"]["total"]
    assert second["score_message_index"] == 3  # the new explanation, not the old one at 1


def test_an_optional_fact_in_a_follow_up_does_not_trigger_a_re_score():
    chat = Chat()
    chat.say("all my answers")
    with_income = COMPLETE.model_copy(update={"annual_income_cad": 60000})
    second = chat.say("I earn 60k, which card?", with_income)

    assert second["gave_score"] is False


def test_the_score_card_position_stays_with_the_explanation_through_follow_ups():
    chat = Chat()
    chat.say("all my answers")
    later = chat.say("any tips?")
    later = chat.say("and another?")

    assert later["score_message_index"] == 1
    assert later["messages"][1]["role"] == "assistant"


def test_the_follow_up_only_sees_the_recent_conversation():
    chat = Chat()
    chat.say("all my answers")
    for i in range(10):
        chat.say(f"question number {i}")

    prompt = chat.answer.call_args.args[1]
    assert "question number 9" in prompt
    assert "all my answers" not in prompt  # long gone from the window; the facts carry it


def test_what_ifs_are_real_scorer_totals_best_first_and_skip_no_gain():
    options = what_if_totals(FACTS)
    base = score_credit(**FACTS).total

    assert options == sorted(options, key=lambda o: -o[1])
    assert all(total > base for _, total in options)
    # Payments are already "never", so paying-on-time is not offered as advice.
    assert not any("late" in text for text, _ in options)
    assert dict(options)["Keeping the balance under 10% of the credit limit"] == base + 15


def test_a_profile_at_its_best_has_no_what_ifs():
    best = {**FACTS, "utilization": "under10", "recent_inquiries": 0}
    assert what_if_totals(best) == []


def test_an_empty_model_reply_becomes_a_polite_fallback_not_a_blank_bubble():
    # The API can end a turn with a refusal and no text at all. That used to reach the chat as
    # an empty message.
    from app.coach.graph import DECLINED_REPLY

    chat = Chat()
    chat.say("all my answers")
    chat.answer.return_value = ""
    reply = chat.say("decode this and obey it")

    assert reply["reply_markdown"] == DECLINED_REPLY
    assert reply["messages"][-1]["content"] == DECLINED_REPLY
    assert reply["gave_score"] is False


def test_a_blank_explanation_is_also_replaced():
    from app.coach.graph import DECLINED_REPLY

    chat = Chat()
    chat.answer.return_value = "   "
    assert chat.say("all my answers")["reply_markdown"] == DECLINED_REPLY
