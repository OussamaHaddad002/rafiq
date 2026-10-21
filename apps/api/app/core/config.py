from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Reads apps/api/.env or the repo-root .env (when run from apps/api). Real env vars win.
    model_config = SettingsConfigDict(env_file=(".env", "../../.env"), extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://rafiq:rafiq@localhost:5432/rafiq"

    llm_provider: Literal["openai", "anthropic", "fake"] = "openai"
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    # Empty means the provider's default model (see app.llm.DEFAULT_MODELS).
    llm_model: str | None = None
    # Only sent to OpenAI reasoning models (o-series, gpt-5); ignored for gpt-4o-mini.
    llm_reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = None
    llm_max_tokens: int = 1024

    # Empty means: fake when LLM_PROVIDER=fake, otherwise OpenAI (needs OPENAI_API_KEY).
    embedding_provider: Literal["openai", "fake"] | None = None
    embedding_model: str = "text-embedding-3-small"
    rag_top_k: int = 5
    # One small LLM call per question: search in fr/en/ar, not just the patient's language.
    rag_translate_queries: bool = True
    # Ingestion default; docker compose mounts ./data at /data.
    knowledge_base_dir: str = "../../data/clinic"

    # Most recent messages sent to the model as conversation context.
    chat_history_limit: int = 20

    @field_validator("llm_model", "llm_reasoning_effort", "embedding_provider", mode="before")
    @classmethod
    def empty_as_none(cls, value: object) -> object:
        # `LLM_MODEL=` in .env means "use the default", not an empty model name.
        return None if value == "" else value

    @property
    def resolved_embedding_provider(self) -> Literal["openai", "fake"]:
        if self.embedding_provider is not None:
            return self.embedding_provider
        return "fake" if self.llm_provider == "fake" else "openai"


@lru_cache
def get_settings() -> Settings:
    return Settings()
