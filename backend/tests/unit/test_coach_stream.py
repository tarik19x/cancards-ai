"""Streaming coach replies: the event protocol, what gets saved, and the endpoint around it.

The model is faked (stream_answer yields chunks we choose), so these cover the plumbing and
the guarantees a stream must keep -- the conversation ends up saved exactly as it would
without streaming -- not the wording of any answer.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from app.coach.graph import (
    DECLINED_REPLY,
    FOLLOW_UP_SYSTEM_PROMPT,
    build_graph,
    resolve_pending_reply,
)
from app.coach.stream import stream_coach_reply
from app.main import app
from app.models import CreditProfile

COMPLETE = CreditProfile(
    card_count=3,
    utilization="10to30",
    history_length="3to7",
    missed_payments="never",
    recent_inquiries=1,
)
PARTIAL = CreditProfile(card_count=3, utilization="10to30")
CONFIG = {"configurable": {"thread_id": "t"}}


@pytest.fixture(autouse=True)
def validation_on(monkeypatch):
    monkeypatch.setattr(
        "app.coach.graph.get_settings", lambda: SimpleNamespace(profile_validation=True)
    )


def fake_stream(*chunks, then_raise=None, calls=None):
    """A stand-in for stream_answer that yields the given chunks."""

    async def _stream(system, user, max_tokens=2000):
        if calls is not None:
            calls.append({"system": system, "user": user, "max_tokens": max_tokens})
        for chunk in chunks:
            yield chunk
        if then_raise:
            raise then_raise

    return _stream


async def events_of(generator) -> list[dict]:
    events = []
    async for raw in generator:
        for line in raw.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
    return events


async def a_turn(graph, profile, message="all my answers"):
    """Run one graph turn with the extractor returning `profile`, without resolving the reply."""
    with patch("app.coach.graph.extract_profile", new_callable=AsyncMock) as extract:
        extract.return_value = profile
        return await graph.ainvoke({"messages": [{"role": "user", "content": message}]}, CONFIG)


async def test_the_reply_arrives_in_chunks_then_a_done_event_with_the_result(monkeypatch):
    graph = build_graph(InMemorySaver())
    state = await a_turn(graph, COMPLETE)
    monkeypatch.setattr("app.coach.stream.stream_answer", fake_stream("Your ", "score ", "is 87."))

    events = await events_of(stream_coach_reply(graph, "t", state))

    assert [e["type"] for e in events] == ["token", "token", "token", "done"]
    assert [e["content"] for e in events[:3]] == ["Your ", "score ", "is 87."]
    done = events[-1]
    assert done["reply_markdown"] == "Your score is 87."
    assert done["gave_score"] is True and done["missing_fields"] == []
    assert done["score"]["total"] == 87 and done["score_message_index"] == 1
    assert done["thread_id"] == "t" and done["turn_count"] == 1


async def test_the_finished_reply_is_saved_so_a_reload_and_the_next_turn_see_it(monkeypatch):
    graph = build_graph(InMemorySaver())
    state = await a_turn(graph, COMPLETE)
    monkeypatch.setattr("app.coach.stream.stream_answer", fake_stream("Here ", "you go."))

    await events_of(stream_coach_reply(graph, "t", state))

    saved = (await graph.aget_state(CONFIG)).values
    assert [m["role"] for m in saved["messages"]] == ["user", "assistant"]
    assert saved["messages"][-1]["content"] == "Here you go."
    assert saved["reply_markdown"] == "Here you go."
    assert saved["pending_reply"] is None


async def test_a_fixed_question_needs_no_model_call_and_goes_out_as_one_event(monkeypatch):
    graph = build_graph(InMemorySaver())
    state = await a_turn(graph, PARTIAL)
    called = []
    monkeypatch.setattr("app.coach.stream.stream_answer", fake_stream(calls=called))

    events = await events_of(stream_coach_reply(graph, "t", state))

    assert called == []  # nothing to wait for, so nothing to stream
    assert [e["type"] for e in events] == ["token", "done"]
    assert "credit" in events[0]["content"].lower()
    assert events[-1]["gave_score"] is False and events[-1]["score"] is None


async def test_an_empty_model_reply_becomes_the_polite_fallback_and_is_saved(monkeypatch):
    graph = build_graph(InMemorySaver())
    state = await a_turn(graph, COMPLETE)
    monkeypatch.setattr("app.coach.stream.stream_answer", fake_stream())

    events = await events_of(stream_coach_reply(graph, "t", state))

    assert events[0] == {"type": "token", "content": DECLINED_REPLY}
    assert events[-1]["reply_markdown"] == DECLINED_REPLY
    assert (await graph.aget_state(CONFIG)).values["messages"][-1]["content"] == DECLINED_REPLY


async def test_a_follow_up_streams_with_the_follow_up_prompt(monkeypatch):
    graph = build_graph(InMemorySaver())
    first = await a_turn(graph, COMPLETE)
    with patch("app.coach.graph.generate_answer", new_callable=AsyncMock) as answer:
        answer.return_value = "the explanation"
        await resolve_pending_reply(graph, CONFIG, first)
    second = await a_turn(graph, COMPLETE, message="how do I raise it?")
    called: list[dict] = []
    monkeypatch.setattr("app.coach.stream.stream_answer", fake_stream("Pay it down.", calls=called))

    events = await events_of(stream_coach_reply(graph, "t", second))

    assert called[0]["system"] == FOLLOW_UP_SYSTEM_PROMPT and called[0]["max_tokens"] == 500
    assert events[-1]["gave_score"] is False
    assert (await graph.aget_state(CONFIG)).values["messages"][-1]["content"] == "Pay it down."


async def test_a_failure_while_streaming_is_an_error_event_that_hides_the_cause(monkeypatch):
    graph = build_graph(InMemorySaver())
    state = await a_turn(graph, COMPLETE)
    monkeypatch.setattr(
        "app.coach.stream.stream_answer",
        fake_stream("half a sentence", then_raise=RuntimeError("key sk-ant-SECRET leaked")),
    )

    events = await events_of(stream_coach_reply(graph, "t", state))

    assert events[-1] == {"type": "error", "message": "Internal server error"}
    assert "SECRET" not in json.dumps(events)


async def test_an_abandoned_stream_does_not_leak_its_prompt_into_the_next_turn():
    # A user who closes the tab mid-reply never reaches the write that clears pending_reply.
    graph = build_graph(InMemorySaver())
    abandoned = await a_turn(graph, COMPLETE)
    assert abandoned["pending_reply"] is not None

    next_turn = await a_turn(graph, PARTIAL, message="hello again")

    assert next_turn["pending_reply"] is None  # reset at the start of every turn
    assert next_turn["gave_score"] is False


# ---- the endpoint ----------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    app.state.coach_graph = build_graph(InMemorySaver())
    monkeypatch.setattr("app.coach.stream.stream_answer", fake_stream("Streamed ", "words."))
    with (
        patch("app.coach.graph.extract_profile", new_callable=AsyncMock) as extract,
        # The plain JSON endpoint resolves its reply with generate_answer; nothing in a unit
        # test may reach the network.
        patch("app.coach.graph.generate_answer", new_callable=AsyncMock) as answer,
    ):
        extract.return_value = COMPLETE
        answer.return_value = "A plain reply."
        test_client = TestClient(app)
        test_client.extract = extract  # type: ignore[attr-defined]
        yield test_client
    del app.state.coach_graph


def parse(response) -> list[dict]:
    return [
        json.loads(line[len("data: ") :])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_the_stream_endpoint_returns_server_sent_events(client):
    response = client.post("/api/coach/chat/stream", json={"message": "everything"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"  # a proxy must not buffer it
    events = parse(response)
    assert events[-1]["type"] == "done" and events[-1]["reply_markdown"] == "Streamed words."
    assert events[-1]["score"]["total"] == 87


def test_a_streamed_conversation_reloads_through_the_thread_endpoint(client):
    done = parse(client.post("/api/coach/chat/stream", json={"message": "everything"}))[-1]

    saved = client.get(f"/api/coach/thread/{done['thread_id']}").json()

    assert [m["role"] for m in saved["messages"]] == ["user", "assistant"]
    assert saved["messages"][-1]["content"] == "Streamed words."
    assert saved["score"]["total"] == 87 and saved["score_message_index"] == 1


def test_a_streamed_turn_continues_the_same_thread_as_a_plain_one(client):
    first = parse(client.post("/api/coach/chat/stream", json={"message": "everything"}))[-1]
    second = client.post(
        "/api/coach/chat", json={"message": "and now?", "thread_id": first["thread_id"]}
    )

    assert second.status_code == 200
    assert second.json()["thread_id"] == first["thread_id"] and second.json()["turn_count"] == 2


def test_the_stream_endpoint_validates_like_the_json_endpoint(client):
    assert client.post("/api/coach/chat/stream", json={"message": ""}).status_code == 422
    bad = client.post("/api/coach/chat/stream", json={"message": "hi", "thread_id": "nope"})
    assert bad.status_code == 422


def test_the_stream_endpoint_is_a_503_when_the_graph_never_started():
    if hasattr(app.state, "coach_graph"):
        del app.state.coach_graph
    response = TestClient(app).post("/api/coach/chat/stream", json={"message": "hi"})
    assert response.status_code == 503
