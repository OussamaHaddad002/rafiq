from typing import Any

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.llm import build_provider
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.fake import FakeProvider
from app.llm.openai_provider import OpenAIProvider


def settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_openai_defaults_to_the_mini_model_with_low_reasoning() -> None:
    provider = build_provider(settings(llm_provider="openai", openai_api_key=SecretStr("k")))
    assert isinstance(provider, OpenAIProvider)
    assert provider._model == "gpt-5.4-mini"
    assert provider._reasoning_effort == "low"


def test_model_can_be_overridden() -> None:
    provider = build_provider(
        settings(llm_provider="openai", openai_api_key=SecretStr("k"), llm_model="gpt-5.4-nano")
    )
    assert isinstance(provider, OpenAIProvider)
    assert provider._model == "gpt-5.4-nano"


@pytest.mark.parametrize("key", [None, SecretStr("")])
def test_missing_openai_key_fails_fast(key: SecretStr | None) -> None:
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        build_provider(settings(llm_provider="openai", openai_api_key=key))


def test_anthropic_and_fake_providers() -> None:
    anthropic = build_provider(settings(llm_provider="anthropic", anthropic_api_key=SecretStr("k")))
    assert isinstance(anthropic, AnthropicProvider)
    assert isinstance(build_provider(settings(llm_provider="fake")), FakeProvider)
