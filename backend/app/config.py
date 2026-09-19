"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # LLM providers
    openai_api_key: str
    anthropic_api_key: str

    # Pinecone
    pinecone_api_key: str
    pinecone_index_name: str = "cancards-index"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"
    # Which named section of the index the app searches. "headers-v1" holds every PDF
    # chunk with its card name written on top (point 1m); "" is the original chunks.
    pinecone_namespace: str = "headers-v1"

    # Retrieval (point 1, measured on the 100 held-out hard questions, recall@8):
    # dense on the original chunks 0.321, hybrid + rerank on the card-name chunks 0.958.
    # RETRIEVAL_MODE=dense with PINECONE_NAMESPACE= (empty) is the old behaviour.
    retrieval_mode: Literal["dense", "hybrid", "hybrid_rerank"] = "hybrid_rerank"

    # Models
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    llm_model: str = "claude-sonnet-4-6"
    llm_provider: str = "anthropic"
    use_mock_llm: bool = False

    # Observability
    langsmith_api_key: str | None = None
    langsmith_project: str = "cancards-ai"
    langsmith_tracing: bool = True

    # App
    app_env: str = "development"
    allowed_origins: str = "http://localhost:3000"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance only reads .env once per process."""
    return Settings()  # type: ignore[call-arg]
