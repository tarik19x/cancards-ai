"""The /api/ask and /api/ask/stream endpoints."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import get_settings
from app.logging_config import get_logger
from app.models import AnswerResponse, AskRequest
from app.rag.generate import generate_response
from app.rag.mock_stream import stream_mock_response
from app.rag.retrieve import retrieve_chunks
from app.rag.stream import stream_rag_response

log = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["ask"])
limiter = Limiter(key_func=get_remote_address)

# UI dev switch — skips embedding, Pinecone, and Claude entirely so I can
# iterate on layout without burning API cost on every keystroke test.
# Set in .env only. Must never be true outside local dev.
settings = get_settings()
USE_MOCK_LLM = settings.use_mock_llm


@router.post("/ask", response_model=AnswerResponse)
@limiter.limit("60/minute")
async def ask(request: Request, body: AskRequest) -> AnswerResponse:
    """Non-streaming ask. Returns complete JSON when ready."""
    try:
        chunks = await retrieve_chunks(body.question, top_k=12)
        if not chunks:
            raise HTTPException(status_code=404, detail="No relevant card information found.")
        response = await generate_response(body.question, chunks)
        log.info(
            "ask_complete",
            question=body.question,
            recommended_count=len(response.recommended_cards),
        )
        return response
    except HTTPException:
        raise
    except Exception as e:
        log.error("ask_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/ask/stream")
@limiter.limit("60/minute")
async def ask_stream(request: Request, body: AskRequest) -> StreamingResponse:
    """Streaming ask. SSE events: token (text chunk), done (final structured response), error."""
    if USE_MOCK_LLM:
        log.info("ask_stream_mock", question=body.question)
        return StreamingResponse(
            stream_mock_response(body.question),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    chunks = await retrieve_chunks(body.question, top_k=12)
    if not chunks:
        raise HTTPException(status_code=404, detail="No relevant card information found.")

    return StreamingResponse(
        stream_rag_response(body.question, chunks),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Disable nginx and any reverse proxy buffering — without this,
            # the proxy might buffer the response and ruin the streaming effect.
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
