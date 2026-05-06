"""FastAPI application entry point."""
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.logging_config import configure_logging, get_logger
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


app = FastAPI(
    title="CanCards AI",
    version="0.1.0",
    description="RAG-powered Q&A for Canadian credit cards",
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
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
