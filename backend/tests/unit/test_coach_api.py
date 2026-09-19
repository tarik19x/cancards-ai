"""The coach HTTP endpoints, through the real FastAPI app.

The graph is built with an in-memory checkpointer and a stubbed language model, so
these tests cover the HTTP contract (thread ids, history reload, error codes) and
not the model's wording.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from app.coach.graph import build_graph
from app.main import app
from app.models import CreditProfile

PARTIAL = CreditProfile(card_count=3, utilization="10to30")
COMPLETE = CreditProfile(
    card_count=3,
    utilization="10to30",
    history_length="3to7",
    missed_payments="never",
    recent_inquiries=1,
)


@pytest.fixture
def client(monkeypatch):
    """A client whose app has a working coach graph (lifespan does not run in tests)."""
    monkeypatch.setattr(
        "app.coach.graph.get_settings", lambda: SimpleNamespace(profile_validation=True)
    )
    app.state.coach_graph = build_graph(InMemorySaver())
    with (
        patch("app.coach.graph.extract_profile", new_callable=AsyncMock) as extract,
        patch("app.coach.graph.generate_answer", new_callable=AsyncMock) as answer,
    ):
        extract.return_value = PARTIAL
        answer.return_value = "Here is what your estimate means."
        test_client = TestClient(app)
        test_client.extract = extract  # type: ignore[attr-defined]
        yield test_client
    del app.state.coach_graph


def test_the_first_message_starts_a_thread_and_asks_the_first_missing_question(client):
    client.extract.return_value = CreditProfile()
    body = client.post("/api/coach/chat", json={"message": "hi"}).json()

    assert body["thread_id"]
    assert body["gave_score"] is False
    assert "how many credit cards" in body["reply_markdown"].lower()
    assert body["missing_fields"][0] == "card_count"


def test_the_returned_thread_id_continues_the_same_conversation(client):
    first = client.post("/api/coach/chat", json={"message": "hi"}).json()
    second = client.post(
        "/api/coach/chat", json={"message": "3 cards", "thread_id": first["thread_id"]}
    ).json()

    assert second["thread_id"] == first["thread_id"]
    assert second["turn_count"] == 2


def test_a_complete_profile_returns_the_computed_score(client):
    client.extract.return_value = COMPLETE
    body = client.post("/api/coach/chat", json={"message": "all my answers"}).json()

    assert body["gave_score"] is True
    assert body["score"]["total"] == 87
    assert body["score"]["band"] == "Very good"
    assert body["missing_fields"] == []


def test_two_clients_get_different_thread_ids(client):
    a = client.post("/api/coach/chat", json={"message": "hi"}).json()["thread_id"]
    b = client.post("/api/coach/chat", json={"message": "hi"}).json()["thread_id"]
    assert a != b


def test_an_empty_message_is_rejected(client):
    assert client.post("/api/coach/chat", json={"message": ""}).status_code == 422


def test_an_overlong_message_is_rejected(client):
    assert client.post("/api/coach/chat", json={"message": "x" * 501}).status_code == 422


def test_history_reloads_a_saved_conversation(client):
    first = client.post("/api/coach/chat", json={"message": "hi"}).json()
    tid = first["thread_id"]
    client.post("/api/coach/chat", json={"message": "3 cards", "thread_id": tid})

    saved = client.get(f"/api/coach/thread/{tid}").json()

    assert [m["role"] for m in saved["messages"]] == ["user", "assistant", "user", "assistant"]
    assert saved["messages"][0]["content"] == "hi"
    assert saved["turn_count"] == 2
    assert saved["profile"]["card_count"] == 3


def test_history_carries_the_score_once_there_is_one(client):
    client.extract.return_value = COMPLETE
    tid = client.post("/api/coach/chat", json={"message": "everything"}).json()["thread_id"]

    saved = client.get(f"/api/coach/thread/{tid}").json()

    assert saved["score"]["total"] == 87
    # The card sits after the explanation (message 1: the user's, then the coach's).
    assert saved["score_message_index"] == 1


UNKNOWN_ID = "00000000-0000-4000-8000-000000000000"


def test_history_for_an_unknown_thread_is_a_404(client):
    assert client.get(f"/api/coach/thread/{UNKNOWN_ID}").status_code == 404


@pytest.mark.parametrize(
    "bad_id",
    [
        "does-not-exist",
        "1",
        "../../etc/passwd",
        "x" * 5000,
        "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA",
        UNKNOWN_ID + "x",
    ],
)
def test_a_conversation_id_that_is_not_a_uuid_is_rejected(client, bad_id):
    assert client.get(f"/api/coach/thread/{bad_id}").status_code in (404, 422)
    posted = client.post("/api/coach/chat", json={"message": "hi", "thread_id": bad_id})
    assert posted.status_code == 422


def test_a_failure_inside_the_graph_is_a_clean_500_not_a_stack_trace(client):
    client.extract.side_effect = RuntimeError("the model is down")
    response = client.post("/api/coach/chat", json={"message": "hi"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "model is down" not in response.text


def test_the_coach_is_a_503_when_the_graph_never_started():
    # No graph on app.state: a failed startup should be a clear 503, not an AttributeError 500.
    if hasattr(app.state, "coach_graph"):
        del app.state.coach_graph
    client = TestClient(app)
    assert client.post("/api/coach/chat", json={"message": "hi"}).status_code == 503
    assert client.get(f"/api/coach/thread/{UNKNOWN_ID}").status_code == 503
