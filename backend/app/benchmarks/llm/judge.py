import json
import logging
import re
from dataclasses import dataclass

from .base import LLMProvider

logger = logging.getLogger(__name__)

# Modelos de razonamiento (MiniMax-M1, DeepSeek-R1, etc.) devuelven su cadena de pensamiento
# envuelta en <think>...</think> ANTES de la respuesta real, incluso cuando response_format
# les pide JSON -- confirmado en vivo contra MiniMax, ver logs del 2026-08-26. Hay que
# descartar ese bloque antes de intentar parsear JSON, o siempre falla.
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_think_block(text: str) -> str:
    return _THINK_BLOCK_RE.sub("", text, count=1).strip()


def _extract_json_object(text: str) -> str:
    """Recorta desde la primera '{' hasta la ultima '}' -- tolerante a un modelo que agrega
    texto explicativo alrededor del JSON pese a que el prompt pide 'SOLO JSON'. Si no hay
    ninguna llave, devuelve el texto tal cual (json.loads fallara y el caller lo maneja)."""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


_COMPLEXITY_LEVELS = ("baja", "media", "alta")
_GREETING_LEVELS = ("ninguno", "casual", "formal")

_PROMPT_TEMPLATE = """Eres un auditor de calidad de atencion al cliente. A continuacion \
esta la transcripcion de una conversacion de WhatsApp entre un agente de soporte y un \
cliente. Tu tarea es evaluar UNICAMENTE el comportamiento del AGENTE (no del cliente):

1. ¿El agente saludo al cliente? Elegi UNA opcion: "ninguno", "casual" o "formal".
   - "ninguno": no hubo ningun saludo, el agente fue directo al tema.
   - "casual": un saludo breve (ej. "Buenos dias", "Hola", "Buenas tardes"), aunque venga \
seguido de inmediato por una pregunta o pedido, sin presentacion mas completa. Ejemplo que SI \
cuenta como "casual" (no como "ninguno"): "Buenos Dias me indica su codigo anydesk para poder \
subirlo".
   - "formal": un saludo mas completo, con presentacion propia y/o de la empresa y/o un \
ofrecimiento explicito de ayuda (ej. "Buenas tardes, gracias por contactar a Casa Market, mi \
nombre es Ana, ¿en que puedo ayudarle?").
2. ¿El agente cerro la conversacion con una despedida?
3. ¿Que tan compleja fue la consulta o problema del cliente? Elegi UNA opcion: "baja", "media" \
o "alta".
4. Considerando esa complejidad, ¿el agente manejo el caso de forma adecuada (con una \
resolucion o derivacion acorde a la dificultad real del caso)?
5. ¿La ortografia y redaccion del AGENTE (no la del cliente) fue correcta, sin errores de \
escritura evidentes? NO cuentes como error la falta de tildes/acentos (muy comun en chat \
informal, ej. "como"/"aqui" sin tilde) -- solo palabras mal escritas o errores de digitacion \
reales.
{transfer_question}
Responde SOLO con un objeto JSON, sin texto adicional, con esta forma exacta:
{{"greeting_level": "ninguno"|"casual"|"formal", "has_farewell": true|false, \
"complexity": "baja"|"media"|"alta", "handled_well_for_complexity": true|false, \
"spelling_ok": true|false{transfer_json_key}, "notes": "una frase breve"}}

Transcripcion:
---
{conversation_text}
---
"""

_TRANSFER_QUESTION = (
    "6. Esta conversacion incluyo una transferencia del caso a otro agente o area. "
    "¿El agente le avisó al cliente, ANTES de transferirlo, que iba a ser transferido?\n"
)
_TRANSFER_JSON_KEY = ', "informed_transfer": true|false'


@dataclass(frozen=True)
class QualityJudgement:
    greeting_level: str | None
    has_farewell: bool | None
    complexity: str | None
    handled_well_for_complexity: bool | None
    spelling_ok: bool | None
    # None cuando la conversacion no tuvo una transferencia real (no aplica) -- distinto de
    # False ("no avisó" implica que sí habia algo que avisar).
    informed_transfer: bool | None
    notes: str | None
    raw: str


def _build_prompt(conversation_text: str, had_transfer: bool) -> str:
    return _PROMPT_TEMPLATE.format(
        conversation_text=conversation_text,
        transfer_question=_TRANSFER_QUESTION if had_transfer else "",
        transfer_json_key=_TRANSFER_JSON_KEY if had_transfer else "",
    )


def judge_conversation(
    provider: LLMProvider, conversation_text: str, had_transfer: bool = False
) -> QualityJudgement:
    """Construye el prompt, llama `provider.complete(prompt)` y parsea el JSON de vuelta de
    forma tolerante -- descarta un posible bloque <think> de razonamiento y recorta al
    objeto JSON antes de parsear (ver _strip_think_block/_extract_json_object); JSON
    malformado o con claves faltantes -> todos los campos de veredicto en None (nunca lanza
    por un solo caso raro, para no tumbar el resto del lote). `raw` siempre guarda la
    respuesta completa y sin tocar (incluido el bloque <think>, si lo hubo) para auditoria --
    solo el parseo ignora ese bloque, no lo que se persiste. Esta funcion no importa ningun
    SDK concreto.

    `had_transfer` decide si el prompt le pregunta al LLM por el aviso de transferencia --
    si es False, ni se le pregunta (evita confundirlo pidiendo algo que no aplica) y
    `informed_transfer` en el resultado queda en None sin importar que responda el modelo."""
    raw = provider.complete(_build_prompt(conversation_text, had_transfer))
    candidate = _extract_json_object(_strip_think_block(raw))
    try:
        data = json.loads(candidate)
    except (ValueError, TypeError) as exc:
        logger.warning("Respuesta del LLM no es JSON valido: %s -- %r", exc, raw[:200])
        return QualityJudgement(
            greeting_level=None,
            has_farewell=None,
            complexity=None,
            handled_well_for_complexity=None,
            spelling_ok=None,
            informed_transfer=None,
            notes=None,
            raw=raw,
        )

    greeting_level = data.get("greeting_level")
    has_farewell = data.get("has_farewell")
    complexity = data.get("complexity")
    handled_well_for_complexity = data.get("handled_well_for_complexity")
    spelling_ok = data.get("spelling_ok")
    informed_transfer = data.get("informed_transfer")
    notes = data.get("notes")
    return QualityJudgement(
        greeting_level=greeting_level if greeting_level in _GREETING_LEVELS else None,
        has_farewell=has_farewell if isinstance(has_farewell, bool) else None,
        complexity=complexity if complexity in _COMPLEXITY_LEVELS else None,
        handled_well_for_complexity=(
            handled_well_for_complexity if isinstance(handled_well_for_complexity, bool) else None
        ),
        spelling_ok=spelling_ok if isinstance(spelling_ok, bool) else None,
        informed_transfer=(
            informed_transfer
            if had_transfer and isinstance(informed_transfer, bool)
            else None
        ),
        notes=notes if isinstance(notes, str) else None,
        raw=raw,
    )
