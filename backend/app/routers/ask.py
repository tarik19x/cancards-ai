"""The /api/ask endpoint - main entry point for Q&A."""
from fastapi import APIRouter, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.logging_config import get_logger
from app.models import AnswerResponse, AskRequest
from app.rag.generate import generate_response
from app.rag.retrieve import retrieve_chunks

log = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["ask"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/ask", response_model=AnswerResponse)
@limiter.limit("60/minute")
async def ask(request: Request, body: AskRequest) -> AnswerResponse:
    """Answer a question about Canadian credit cards."""
    try:
        chunks = await retrieve_chunks(body.question, top_k=12)
        if not chunks:
            raise HTTPException(
                status_code=404,
                detail="No relevant card information found.",
            )
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
