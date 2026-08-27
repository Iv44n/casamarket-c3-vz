import pytest

from app.benchmarks import llm, settings
from app.benchmarks.llm.openai_provider import OpenAIProvider


def test_build_provider_minimax_reuses_openai_provider_with_a_custom_base_url():
    llm_config = settings.LLMConfig(
        provider_name="minimax",
        minimax_api_key="mm-secreta",
        minimax_model="MiniMax-M1",
        minimax_base_url="https://api.minimax.io/v1",
    )

    provider = llm.build_provider(llm_config)

    assert isinstance(provider, OpenAIProvider)
    assert provider.model == "MiniMax-M1"
    assert str(provider.client.base_url) == "https://api.minimax.io/v1/"
    assert str(provider.client.api_key) == "mm-secreta"


def test_build_provider_minimax_raises_when_any_field_is_missing():
    llm_config = settings.LLMConfig(provider_name="minimax", minimax_api_key="mm-secreta")

    with pytest.raises(ValueError, match="minimax"):
        llm.build_provider(llm_config)


def test_build_provider_raises_for_an_unknown_provider():
    llm_config = settings.LLMConfig(provider_name="anthropic")

    with pytest.raises(ValueError, match="anthropic"):
        llm.build_provider(llm_config)
