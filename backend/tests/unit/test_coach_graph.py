"""The coach graph's routing, scoring and memory -- no real LLM or database calls.

extract_profile and generate_answer are stubbed, so these tests pin the behaviour
the premature-advice measurement depends on rather than the model's wording.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.coach.graph import build_graph
from app.coach.scoring import score_credit
from app.models import CreditProfile

COMPLETE = CreditProfile(
    card_count=3,
    utilization="10to30",
    history_length="3to7",
    missed_payments="never",
    recent_inquiries=1,
)
PARTIAL = CreditProfile(card_count=3, utilization="10to30")


@pytest.fixture
def validation_on(monkeypatch):
    monkeypatch.setattr(
        "app.coach.graph.get_settings", lambda: SimpleNamespace(profile_validation=True)
    )


@pytest.fixture
def validation_off(monkeypatch):
    monkeypatch.setattr(
        "app.coach.graph.get_settings", lambda: SimpleNamespace(profile_validation=False)
    )


def _run(profile: CreditProfile, message: str = "how is my credit?", reply: str = "explained"):
    """Invoke one turn with the extractor returning `profile`."""
    with (
        patch("app.coach.graph.extract_profile", new_callable=AsyncMock) as mock_extract,
        patch("app.coach.graph.generate_answer", new_callable=AsyncMock) as mock_answer,
    ):
        mock_extract.return_value = profile
        mock_answer.return_value = reply
        graph = build_graph(InMemorySaver())
        import asyncio

        state = asyncio.run(
            graph.ainvoke(
                {"messages": [{"role": "user", "content": message}]},
                config={"configurable": {"thread_id": "t1"}},
            )
        )
        return state, mock_answer


def test_an_incomplete_profile_is_asked_about_not_scored(validation_on):
    state, mock_answer = _run(PARTIAL)

    assert state["gave_score"] is False
    assert state["score"] is None
    assert state["missing_fields"] == ["history_length", "missed_payments", "recent_inquiries"]
    # No language model was called at all: the question comes from the field table.
    mock_answer.assert_not_called()


def test_the_question_asked_is_the_earliest_missing_fact(validation_on):
    state, _ = _run(PARTIAL)
    assert "oldest credit card" in state["reply_markdown"]


def test_a_complete_profile_is_scored_and_explained(validation_on):
    state, mock_answer = _run(COMPLETE)

    assert state["gave_score"] is True
    assert state["score"] is not None
    assert state["missing_fields"] == []
    mock_answer.assert_called_once()


def test_the_score_comes_from_the_deterministic_scorer_not_the_model(validation_on):
    state, _ = _run(COMPLETE)
    expected = score_credit(
        card_count=3,
        utilization="10to30",
        history_length="3to7",
        missed_payments="never",
        recent_inquiries=1,
    )
    assert state["score"]["total"] == expected.total
    assert state["score"]["band"] == expected.band


def test_the_explanation_is_given_the_real_numbers_to_quote(validation_on):
    _, mock_answer = _run(COMPLETE)
    prompt = mock_answer.call_args.args[1]
    assert "/100" in prompt and "Payment history" in prompt


def test_with_validation_off_an_incomplete_profile_still_gets_an_answer(validation_off):
    # The "before" configuration, and the behaviour the premature-advice rate counts:
    # the model is asked to answer anyway, with facts missing.
    state, mock_answer = _run(PARTIAL)

    assert state["gave_score"] is True
    assert state["score"] is None  # nothing was computed; the model guessed
    mock_answer.assert_called_once()


def test_with_validation_off_a_complete_profile_is_still_scored_properly(validation_off):
    # Switching the gate off must not change the arithmetic, only who gets held back.
    # 35 never + 24 (10-30%) + 11 (3-7 yrs) + 7 (one inquiry) + 10 (3 cards) = 87.
    state, _ = _run(COMPLETE)
    assert state["score"]["total"] == 87
    assert state["score"]["band"] == "Very good"


def test_scoring_never_runs_on_a_partial_profile_even_with_the_gate_off(validation_off):
    # The gate is a routing decision; the scorer independently refuses to invent
    # a number from missing facts.
    state, _ = _run(PARTIAL)
    assert state["score"] is None


def test_a_thread_remembers_earlier_turns(validation_on):
    import asyncio

    with (
        patch("app.coach.graph.extract_profile", new_callable=AsyncMock) as mock_extract,
        patch("app.coach.graph.generate_answer", new_callable=AsyncMock) as mock_answer,
    ):
        mock_answer.return_value = "explained"
        graph = build_graph(InMemorySaver())
        config = {"configurable": {"thread_id": "same-thread"}}

        mock_extract.return_value = PARTIAL
        asyncio.run(graph.ainvoke({"messages": [{"role": "user", "content": "hi"}]}, config))
        mock_extract.return_value = COMPLETE
        second = asyncio.run(
            graph.ainvoke({"messages": [{"role": "user", "content": "3 to 7 years"}]}, config)
        )

        # Both user turns and the question asked in between are still there.
        assert [m["role"] for m in second["messages"]] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]
        assert second["turn_count"] == 2
        # The extractor was handed the whole conversation, not just the new message.
        assert len(mock_extract.call_args.args[0]) == 3


def test_two_threads_do_not_see_each_others_conversations(validation_on):
    import asyncio

    with (
        patch("app.coach.graph.extract_profile", new_callable=AsyncMock) as mock_extract,
        patch("app.coach.graph.generate_answer", new_callable=AsyncMock) as mock_answer,
    ):
        mock_answer.return_value = "explained"
        mock_extract.return_value = PARTIAL
        graph = build_graph(InMemorySaver())

        asyncio.run(
            graph.ainvoke(
                {"messages": [{"role": "user", "content": "first"}]},
                config={"configurable": {"thread_id": "a"}},
            )
        )
        other = asyncio.run(
            graph.ainvoke(
                {"messages": [{"role": "user", "content": "second"}]},
                config={"configurable": {"thread_id": "b"}},
            )
        )

    assert other["turn_count"] == 1
    assert [m["content"] for m in other["messages"] if m["role"] == "user"] == ["second"]
