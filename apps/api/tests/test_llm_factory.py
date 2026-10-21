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


def test_openai_defaults_to_gpt_4o_mini_without_reasoning() -> None:
    provider = build_provider(settings(llm_provider="openai", openai_api_key=SecretStr("k")))
    assert isinstance(provider, OpenAIProvider)
    assert provider._model == "gpt-4o-mini"
    assert provider._reasoning_effort is None


def test_reasoning_effort_is_ignored_for_non_reasoning_models() -> None:
    provider = build_provider(
        settings(llm_provider="openai", openai_api_key=SecretStr("k"), llm_reasoning_effort="low")
    )
    assert isinstance(provider, OpenAIProvider)
    assert provider._reasoning_effort is None


def test_empty_env_values_mean_defaults() -> None:
    s = settings(llm_model="", llm_reasoning_effort="", embedding_provider="")
    assert (s.llm_model, s.llm_reasoning_effort, s.embedding_provider) == (None, None, None)


def test_embedding_provider_follows_llm_provider_by_default() -> None:
    assert settings(llm_provider="fake").resolved_embedding_provider == "fake"
    assert settings(llm_provider="anthropic").resolved_embedding_provider == "openai"
    assert (
        settings(llm_provider="fake", embedding_provider="openai").resolved_embedding_provider
        == "openai"
    )


def test_model_can_be_overridden() -> None:
    provider = build_provider(
        settings(llm_provider="openai", openai_api_key=SecretStr("k"), llm_model="gpt-4.1-nano")
    )
    assert isinstance(provider, OpenAIProvider)
    assert provider._model == "gpt-4.1-nano"


@pytest.mark.parametrize("key", [None, SecretStr("")])
def test_missing_openai_key_fails_fast(key: SecretStr | None) -> None:
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        build_provider(settings(llm_provider="openai", openai_api_key=key))


def test_anthropic_and_fake_providers() -> None:
    anthropic = build_provider(settings(llm_provider="anthropic", anthropic_api_key=SecretStr("k")))
    assert isinstance(anthropic, AnthropicProvider)
    assert isinstance(build_provider(settings(llm_provider="fake")), FakeProvider)
