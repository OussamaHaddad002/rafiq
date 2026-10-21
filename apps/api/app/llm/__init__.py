from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMProvider
from app.llm.fake import FakeProvider
from app.llm.openai_provider import OpenAIProvider

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-5-5",
}


def require_key(key: SecretStr | None, env_name: str, used_for: str) -> str:
    value = key.get_secret_value() if key else ""
    if not value:
        raise RuntimeError(
            f"{env_name} is required for {used_for} (set LLM_PROVIDER=fake to run without a key)."
        )
    return value


def build_provider(settings: Settings) -> LLMProvider:
    provider = settings.llm_provider
    if provider == "fake":
        return FakeProvider()
    model = settings.llm_model or DEFAULT_MODELS[provider]
    if provider == "openai":
        return OpenAIProvider(
            api_key=require_key(settings.openai_api_key, "OPENAI_API_KEY", "LLM_PROVIDER=openai"),
            model=model,
            reasoning_effort=settings.llm_reasoning_effort,
        )
    return AnthropicProvider(
        api_key=require_key(
            settings.anthropic_api_key, "ANTHROPIC_API_KEY", "LLM_PROVIDER=anthropic"
        ),
        model=model,
    )


@lru_cache
def get_provider() -> LLMProvider:
    return build_provider(get_settings())


ProviderDep = Annotated[LLMProvider, Depends(get_provider)]
