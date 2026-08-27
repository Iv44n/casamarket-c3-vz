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


_PROMPT_TEMPLATE = """Eres un auditor de calidad de atencion al cliente. A continuacion \
esta la transcripcion de una conversacion de WhatsApp entre un agente de soporte y un \
cliente. Tu tarea es evaluar UNICAMENTE el comportamiento del AGENTE (no del cliente):

1. ¿El agente abrio la conversacion con un saludo/presentacion?
2. ¿El agente cerro la conversacion con una despedida?

Responde SOLO con un objeto JSON, sin texto adicional, con esta forma exacta:
{{"has_greeting": true|false, "has_farewell": true|false, "notes": "una frase breve"}}

Transcripcion:
---
{conversation_text}
---
"""


@dataclass(frozen=True)
class QualityJudgement:
    has_greeting: bool | None
    has_farewell: bool | None
    notes: str | None
    raw: str


def _build_prompt(conversation_text: str) -> str:
    return _PROMPT_TEMPLATE.format(conversation_text=conversation_text)


def judge_conversation(provider: LLMProvider, conversation_text: str) -> QualityJudgement:
    """Construye el prompt, llama `provider.complete(prompt)` y parsea el JSON de vuelta de
    forma tolerante -- descarta un posible bloque <think> de razonamiento y recorta al
    objeto JSON antes de parsear (ver _strip_think_block/_extract_json_object); JSON
    malformado o con claves faltantes -> has_greeting/has_farewell = None (nunca lanza por
    un solo caso raro, para no tumbar el resto del lote). `raw` siempre guarda la respuesta
    completa y sin tocar (incluido el bloque <think>, si lo hubo) para auditoria -- solo el
    parseo ignora ese bloque, no lo que se persiste. Esta funcion no importa ningun SDK
    concreto."""
    raw = provider.complete(_build_prompt(conversation_text))
    candidate = _extract_json_object(_strip_think_block(raw))
    try:
        data = json.loads(candidate)
    except (ValueError, TypeError) as exc:
        logger.warning("Respuesta del LLM no es JSON valido: %s -- %r", exc, raw[:200])
        return QualityJudgement(has_greeting=None, has_farewell=None, notes=None, raw=raw)

    has_greeting = data.get("has_greeting")
    has_farewell = data.get("has_farewell")
    notes = data.get("notes")
    return QualityJudgement(
        has_greeting=has_greeting if isinstance(has_greeting, bool) else None,
        has_farewell=has_farewell if isinstance(has_farewell, bool) else None,
        notes=notes if isinstance(notes, str) else None,
        raw=raw,
    )
