from ... import config
from .base import LLMProvider
from .judge import QualityJudgement, judge_conversation
from .openai_provider import build_openai_provider

__all__ = ["LLMProvider", "QualityJudgement", "judge_conversation", "build_provider"]


def build_provider(llm_config: "config.LLMConfig") -> LLMProvider:
    """Factory que despacha por `llm_config.provider_name` -- hoy solo existe la rama
    'minimax'. Agregar un proveedor nuevo con formato propio es una clase nueva (ver
    openai_provider.py) + una rama nueva aca, sin tocar judge.py ni benchmarks/pipeline.py.
    Un proveedor compatible con la API de OpenAI (como MiniMax) ni siquiera necesita una
    clase nueva -- reusa OpenAIProvider con su propio base_url."""
    if llm_config.provider_name == "minimax":
        has_all_fields = (
            llm_config.minimax_api_key
            and llm_config.minimax_model
            and llm_config.minimax_base_url
        )
        if not has_all_fields:
            raise ValueError(
                "LLMConfig.minimax_api_key/minimax_model/minimax_base_url son requeridos "
                "cuando provider_name='minimax'."
            )
        return build_openai_provider(
            llm_config.minimax_api_key,
            llm_config.minimax_model,
            base_url=llm_config.minimax_base_url,
        )

    raise ValueError(f"Proveedor de LLM desconocido: {llm_config.provider_name!r}.")
