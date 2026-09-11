from .. import settings
from .anthropic_provider import build_anthropic_provider
from .base import LLMProvider
from .judge import QualityJudgement, judge_conversation
from .openai_provider import build_openai_provider

__all__ = ["LLMProvider", "QualityJudgement", "judge_conversation", "build_provider"]

# provider_name -> (default_base_url, use_json_response_format) para los proveedores que
# hablan el formato de API que popularizo OpenAI (Chat Completions + response_format) --
# todos reusan OpenAIProvider tal cual, solo con su propio api_key/modelo/base_url por
# default. El admin puede pisar ese default via LLMConfig.base_url (por ejemplo, para
# apuntar "minimax" a OpenRouter en vez de la API oficial de MiniMax, sin tocar codigo).
#
# use_json_response_format=True para los 4 -- confirmado que MiniMax lo soporta en vivo
# (judge.py ya depende de esto desde antes); OpenAI y DeepSeek lo documentan igual
# (`response_format: {"type": "json_object"}` en su Chat Completions); la capa de
# compatibilidad con OpenAI de Gemini tambien lo acepta. Si algun proveedor nuevo no lo
# soportara, el parseo tolerante de judge.py (_strip_think_block/_extract_json_object) sigue
# funcionando igual sin el -- json_object es una ayuda, no una dependencia dura.
_OPENAI_COMPATIBLE_DEFAULTS: dict[str, tuple[str, bool]] = {
    "minimax": ("https://api.minimax.io/v1", True),
    "deepseek": ("https://api.deepseek.com", True),
    "openai": ("https://api.openai.com/v1", True),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", True),
}


def build_provider(llm_config: "settings.LLMConfig") -> LLMProvider:
    """Strategy factory: `llm_config.provider_name` elige que implementacion de LLMProvider
    construir, sin que pipeline.py/judge.py necesiten saber cual es -- las dos cumplen el
    mismo contrato de un solo metodo (base.py). Agregar un proveedor OpenAI-compatible nuevo
    es una entrada nueva en _OPENAI_COMPATIBLE_DEFAULTS, sin clase propia; agregar uno con
    API realmente distinta (como Claude) es una clase nueva (ver anthropic_provider.py) mas
    una rama nueva aca, sin tocar los proveedores ya existentes."""
    if not llm_config.api_key or not llm_config.model:
        raise ValueError(
            "LLMConfig.api_key/model son requeridos sin importar el proveedor elegido."
        )

    if llm_config.provider_name in _OPENAI_COMPATIBLE_DEFAULTS:
        default_base_url, use_json_response_format = _OPENAI_COMPATIBLE_DEFAULTS[
            llm_config.provider_name
        ]
        return build_openai_provider(
            llm_config.api_key,
            llm_config.model,
            base_url=llm_config.base_url or default_base_url,
            use_json_response_format=use_json_response_format,
        )

    if llm_config.provider_name == "claude":
        return build_anthropic_provider(llm_config.api_key, llm_config.model)

    raise ValueError(f"Proveedor de LLM desconocido: {llm_config.provider_name!r}.")
