import pytest

from app.benchmarks import llm, settings
from app.benchmarks.llm.anthropic_provider import AnthropicProvider
from app.benchmarks.llm.openai_provider import OpenAIProvider


def test_build_provider_minimax_reuses_openai_provider_with_a_custom_base_url():
    llm_config = settings.LLMConfig(
        provider_name="minimax",
        api_key="mm-secreta",
        model="MiniMax-M1",
        base_url="https://api.minimax.io/v1",
    )

    provider = llm.build_provider(llm_config)

    assert isinstance(provider, OpenAIProvider)
    assert provider.model == "MiniMax-M1"
    assert str(provider.client.base_url) == "https://api.minimax.io/v1/"
    assert str(provider.client.api_key) == "mm-secreta"


@pytest.mark.parametrize(
    "provider_name, expected_base_url",
    [
        ("minimax", "https://api.minimax.io/v1/"),
        ("deepseek", "https://api.deepseek.com"),
        ("openai", "https://api.openai.com/v1/"),
        ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/"),
    ],
)
def test_build_provider_uses_each_openai_compatible_providers_own_default_base_url(
    provider_name, expected_base_url
):
    llm_config = settings.LLMConfig(
        provider_name=provider_name, api_key="secreta", model="algun-modelo"
    )

    provider = llm.build_provider(llm_config)

    assert isinstance(provider, OpenAIProvider)
    assert str(provider.client.base_url) == expected_base_url


def test_build_provider_lets_an_explicit_base_url_override_the_default():
    """Ver LLMConfig.base_url -- el caso de uso real es apuntar "minimax" a OpenRouter en
    vez de la API oficial de MiniMax, sin tocar codigo."""
    llm_config = settings.LLMConfig(
        provider_name="minimax",
        api_key="or-secreta",
        model="minimax/minimax-m1",
        base_url="https://openrouter.ai/api/v1",
    )

    provider = llm.build_provider(llm_config)

    assert str(provider.client.base_url) == "https://openrouter.ai/api/v1/"


def test_build_provider_claude_uses_the_anthropic_provider():
    llm_config = settings.LLMConfig(
        provider_name="claude", api_key="sk-ant-secreta", model="claude-sonnet-5"
    )

    provider = llm.build_provider(llm_config)

    assert isinstance(provider, AnthropicProvider)
    assert provider.model == "claude-sonnet-5"
    assert str(provider.client.api_key) == "sk-ant-secreta"


def test_build_provider_raises_when_api_key_or_model_is_missing():
    llm_config = settings.LLMConfig(provider_name="minimax", api_key="mm-secreta")

    with pytest.raises(ValueError, match="api_key/model"):
        llm.build_provider(llm_config)


def test_build_provider_raises_for_an_unknown_provider():
    llm_config = settings.LLMConfig(
        provider_name="llama", api_key="secreta", model="algun-modelo"
    )

    with pytest.raises(ValueError, match="llama"):
        llm.build_provider(llm_config)
