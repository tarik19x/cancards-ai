"""Application configuration loaded from environment variables."""

from functools import lru_cache

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

    # Models
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    llm_model: str = "claude-sonnet-4-6"
    llm_provider: str = "anthropic"

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
    """Cached settings instance â€” only reads .env once per process."""
    return Settings()  # type: ignore[call-arg]
