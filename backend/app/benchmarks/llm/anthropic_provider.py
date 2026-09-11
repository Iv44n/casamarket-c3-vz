from dataclasses import dataclass

from anthropic import Anthropic

# El prompt de judge.py ya le pide "SOLO un objeto JSON, sin texto adicional" como texto
# plano -- a diferencia de los 4 proveedores compatibles con OpenAI (openai_provider.py),
# la Messages API de Anthropic no tiene un response_format=json_object equivalente, asi que
# Claude depende integramente de seguir esa instruccion. El parseo tolerante de judge.py
# (_strip_think_block/_extract_json_object) ya cubre esto como red de seguridad para
# cualquier proveedor, no es algo especial de este archivo.
#
# La respuesta esperada es chica (el JSON del veredicto + una nota de 2-4 oraciones), asi
# que un limite fijo alcanza de sobra sin necesitar que sea configurable.
_MAX_OUTPUT_TOKENS = 1024


@dataclass
class AnthropicProvider:
    client: Anthropic
    model: str

    def complete(self, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=_MAX_OUTPUT_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


def build_anthropic_provider(api_key: str, model: str) -> AnthropicProvider:
    # max_retries=0: mismo motivo que openai_provider.py -- un 429 de cuota agotada nunca se
    # arregla reintentando, y pipeline.py ya corta el resto del batch al primer 429 (detectado
    # via getattr(exc, "status_code", None), que tambien vale para las excepciones del SDK de
    # Anthropic -- son del mismo estilo "Stainless" que las de openai, con .status_code).
    return AnthropicProvider(client=Anthropic(api_key=api_key, max_retries=0), model=model)
