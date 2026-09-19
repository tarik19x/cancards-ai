"""FastAPI application entry point."""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware  # Cross-Origin Resource Sharing (CORS)
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.logging_config import configure_logging, get_logger
from app.rag.bm25_index import get_bm25_corpus
from app.routers import ask, cards, health

settings = get_settings()
configure_logging(settings.log_level)
log = get_logger(__name__)

# LangSmith tracing
if settings.langsmith_tracing and settings.langsmith_api_key:
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    log.info("langsmith_enabled", project=settings.langsmith_project)


async def _warm_keyword_index() -> None:
    """Build the keyword index in the background so the first question does not pay for
    downloading the corpus. Not awaited by startup: a slow or failing Pinecone read must not
    hold up the container's health check, and a failure just means the first hybrid
    request tries again (and falls back to dense if that fails too).
    """
    try:
        await asyncio.to_thread(get_bm25_corpus)
    except Exception as exc:
        log.warning("keyword_index_warmup_failed", error=str(exc))


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    warmup = None
    if settings.retrieval_mode != "dense":
        warmup = asyncio.create_task(_warm_keyword_index())
    yield
    if warmup is not None and not warmup.done():
        warmup.cancel()


app = FastAPI(
    title="CanCards AI",
    version="0.1.0",
    description="RAG-powered Q&A for Canadian credit cards",
    lifespan=lifespan,
)

# CORS (frontend on Vercel will hit this)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Rate limiting handler
app.state.limiter = ask.limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# Routers
app.include_router(health.router)
app.include_router(ask.router)
app.include_router(cards.router)


@app.get("/")
async def root() -> dict:
    return {
        "name": "CanCards AI",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
