"""Streaming replies for the Credit Coach.

The score explanation and the follow-up answers are the slow part of a turn: Claude writing
about 150 words takes several seconds, and until now the user saw nothing until it finished.
This sends the words as they are written instead. Same event shape as the Ask page's
stream (app/rag/stream.py): `token` events with a text chunk, one final `done` event with
the structured result, or an `error` event, so the frontend can share one reading pattern.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

from app.clients.anthropic_client import stream_answer
from app.coach.graph import DECLINED_REPLY
from app.coach.scoring import ScoreResult
from app.logging_config import get_logger
from app.models import CreditProfile

log = get_logger(__name__)


def _event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def stream_coach_reply(
    graph: Any, thread_id: str, state: dict[str, Any]
) -> AsyncIterator[str]:
    """Yield the server-sent events for one coach turn.

    `state` is what graph.ainvoke() returned for this turn. With no pending_reply the reply
    is already known (a fixed question: no model call, so nothing to wait for) and goes out
    as a single token event. Otherwise the reply is streamed from Claude and then written
    into the graph's saved state exactly as resolve_pending_reply would, so the next turn's
    history and a page reload see the same conversation whichever path produced it.
    """
    pending = state.get("pending_reply")
    try:
        if pending is None:
            full_text = state.get("reply_markdown", "")
            if full_text:
                yield _event({"type": "token", "content": full_text})
        else:
            full_text = ""
            async for chunk in stream_answer(
                pending["system"], pending["user"], max_tokens=pending["max_tokens"]
            ):
                full_text += chunk
                if chunk:
                    yield _event({"type": "token", "content": chunk})

            if not full_text.strip():
                # The API can end a turn with a refusal and no text at all.
                log.warning("model_returned_no_text")
                full_text = DECLINED_REPLY
                yield _event({"type": "token", "content": full_text})

            await graph.aupdate_state(
                {"configurable": {"thread_id": thread_id}},
                {
                    "messages": [{"role": "assistant", "content": full_text}],
                    "reply_markdown": full_text,
                    "pending_reply": None,
                },
                as_node="follow_up" if pending["kind"] == "follow_up" else "explain",
            )

        score = state.get("score")
        profile = CreditProfile.model_validate(state.get("profile") or {})
        yield _event(
            {
                "type": "done",
                "thread_id": thread_id,
                "reply_markdown": full_text,
                "profile": json.loads(profile.model_dump_json()),
                "missing_fields": state.get("missing_fields", []),
                "gave_score": bool(state.get("gave_score")),
                "score": (
                    json.loads(ScoreResult.model_validate(score).model_dump_json())
                    if score
                    else None
                ),
                "score_message_index": state.get("score_message_index") if score else None,
                "turn_count": state.get("turn_count", 0),
            }
        )
    except Exception as exc:
        # Nothing from the exception reaches the client: it can carry a prompt or a key.
        log.error("coach_stream_failed", thread_id=thread_id, error=str(exc), exc_info=True)
        yield _event({"type": "error", "message": "Internal server error"})
