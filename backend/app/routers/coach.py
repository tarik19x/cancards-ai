"""The /api/coach/chat endpoint: one turn of a Credit Coach conversation."""

import uuid

from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import StreamingResponse
from starlette.requests import Request

from app.coach.graph import resolve_pending_reply
from app.coach.profile import missing_fields
from app.coach.scoring import ScoreResult
from app.coach.stream import stream_coach_reply
from app.logging_config import get_logger
from app.models import (
    THREAD_ID_PATTERN,
    ChatRequest,
    ChatResponse,
    CreditProfile,
    ThreadMessage,
    ThreadResponse,
)
from app.routers.ask import limiter

log = get_logger(__name__)
router = APIRouter(prefix="/api/coach", tags=["coach"])


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("30/minute")
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    """Send one message. Pass the returned thread_id back to continue the conversation.

    The graph is compiled once at startup and shared; the thread_id is what keeps
    conversations apart, and the checkpointer reloads that thread's state before
    the first node runs, so nothing about the history is sent by the client.
    """
    graph = getattr(request.app.state, "coach_graph", None)
    if graph is None:  # startup failed to build it; better a clear 503 than an attribute error
        raise HTTPException(status_code=503, detail="Coach is unavailable.")

    # A client that sends no thread_id is starting a new conversation. The id is
    # minted here rather than by the client so one client cannot read another's
    # thread by guessing a short id.
    thread_id = body.thread_id or str(uuid.uuid4())

    config = {"configurable": {"thread_id": thread_id}}
    try:
        # durability="exit": save the state once when the turn finishes, not after each of its
        # 3-4 graph steps. The saver runs one database operation at a time, so with 15 users
        # those extra writes queued behind each other (10 s a turn instead of 2 s, measured).
        # A turn is all-or-nothing anyway: if the process dies mid-turn the user just resends.
        state = await graph.ainvoke(
            {"messages": [{"role": "user", "content": body.message}]},
            config=config,
            durability="exit",
        )
        # The graph decides and scores; the reply text for an explanation or follow-up is
        # generated here, in one call, for clients that want plain JSON. /chat/stream below
        # streams the same text instead.
        state = await resolve_pending_reply(graph, config, state)
    except Exception as exc:
        log.error("coach_turn_failed", thread_id=thread_id, error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    score = state.get("score")
    log.info(
        "coach_turn",
        thread_id=thread_id,
        turn=state.get("turn_count", 0),
        gave_score=bool(state.get("gave_score")),
        missing=state.get("missing_fields", []),
    )
    return ChatResponse(
        thread_id=thread_id,
        reply_markdown=state.get("reply_markdown", ""),
        profile=CreditProfile.model_validate(state.get("profile") or {}),
        missing_fields=state.get("missing_fields", []),
        gave_score=bool(state.get("gave_score")),
        score=ScoreResult.model_validate(score) if score else None,
        score_message_index=state.get("score_message_index") if score else None,
        turn_count=state.get("turn_count", 0),
    )


@router.post("/chat/stream")
@limiter.limit("30/minute")
async def chat_stream(request: Request, body: ChatRequest) -> StreamingResponse:
    """One turn, streamed. SSE events: token (a text chunk), done (the structured result), error.

    The fast part of the turn (reading the facts, scoring, routing) runs first; the slow part,
    Claude writing the explanation or the follow-up answer, is then sent word by word, so
    the user sees the reply start after the first few words instead of after the last.
    """
    graph = getattr(request.app.state, "coach_graph", None)
    if graph is None:
        raise HTTPException(status_code=503, detail="Coach is unavailable.")

    thread_id = body.thread_id or str(uuid.uuid4())
    try:
        state = await graph.ainvoke(
            {"messages": [{"role": "user", "content": body.message}]},
            config={"configurable": {"thread_id": thread_id}},
            durability="exit",
        )
    except Exception as exc:
        log.error("coach_turn_failed", thread_id=thread_id, error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    log.info(
        "coach_turn",
        thread_id=thread_id,
        turn=state.get("turn_count", 0),
        gave_score=bool(state.get("gave_score")),
        missing=state.get("missing_fields", []),
        streamed=state.get("pending_reply") is not None,
    )
    return StreamingResponse(
        stream_coach_reply(graph, thread_id, state),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Same as /ask/stream: stop a reverse proxy from buffering the stream, which would
            # bring back the wait this endpoint exists to remove.
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/thread/{thread_id}", response_model=ThreadResponse)
@limiter.limit("60/minute")
async def get_thread(
    request: Request, thread_id: str = Path(pattern=THREAD_ID_PATTERN)
) -> ThreadResponse:
    """Reload a saved conversation, so a refreshed page picks up where it left off.

    The history lives in the checkpointer (Postgres when DATABASE_URL is set), not in
    the browser: the client keeps only the thread_id.
    """
    graph = getattr(request.app.state, "coach_graph", None)
    if graph is None:
        raise HTTPException(status_code=503, detail="Coach is unavailable.")

    snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    values = snapshot.values
    # An unknown id and an empty one look the same to the checkpointer; both are "no such thread".
    if not values or not values.get("messages"):
        raise HTTPException(status_code=404, detail="Conversation not found.")

    profile = CreditProfile.model_validate(values.get("profile") or {})
    score = values.get("score")
    return ThreadResponse(
        thread_id=thread_id,
        messages=[ThreadMessage(**m) for m in values["messages"]],
        profile=profile,
        missing_fields=missing_fields(profile),
        score=ScoreResult.model_validate(score) if score else None,
        score_message_index=values.get("score_message_index") if score else None,
        turn_count=values.get("turn_count", 0),
    )
