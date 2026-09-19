"""The /api/coach/chat endpoint: one turn of a Credit Coach conversation."""

import uuid

from fastapi import APIRouter, HTTPException
from starlette.requests import Request

from app.coach.scoring import ScoreResult
from app.logging_config import get_logger
from app.models import ChatRequest, ChatResponse, CreditProfile
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

    try:
        state = await graph.ainvoke(
            {"messages": [{"role": "user", "content": body.message}]},
            config={"configurable": {"thread_id": thread_id}},
        )
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
        turn_count=state.get("turn_count", 0),
    )
