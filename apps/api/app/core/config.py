from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
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
    # OpenAI reasoning models only. Reasoning tokens are billed as output tokens.
    llm_reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = "low"
    llm_max_tokens: int = 1024

    # Most recent messages sent to the model as conversation context.
    chat_history_limit: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
