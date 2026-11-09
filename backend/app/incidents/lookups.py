"""Sugerencias para el formulario de incidencias manuales: agentes y clientes (con su telefono).

Salen de los datos que ya hay en Turso, no de C3 en vivo (el equipo ya no tiene acceso):
- Agentes: la columna `agente` de las 4 tablas de casos.
- Clientes: el padron de contactos (ultima captura), los clientes de las atenciones y los que ya
  se escribieron a mano en incidencias manuales. Como de C3 ya no entran datos nuevos, esta
  ultima fuente es la que hace que un cliente o agente nuevo aparezca la proxima vez.

Las sugerencias nunca bloquean: el formulario acepta texto libre, esto solo ahorra tipeo.

Cache en memoria (plain dict + Lock, mismo supuesto de un solo proceso que auth/dependencies.py):
armar el indice de C3 cuesta varios segundos en Turso (medido 2026-11-09: ~4s solo los clientes de
atenciones), asi que se calcula una vez y se reusa. Lo registrado a mano cambia seguido, tiene su
propio cache corto y se invalida al crear/editar/borrar una incidencia."""

import logging
import re
import threading
import time
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Generic, TypeVar

from ..extraction import store as extraction_store
from . import store as incidents_store

logger = logging.getLogger(__name__)

MIN_QUERY_CHARS = 2
MIN_QUERY_DIGITS = 3
MAX_RESULTS = 12

# El historial de C3 ya no crece (sin acceso) y el padron es una foto: un TTL largo alcanza.
_C3_TTL_SECONDS = 6 * 60 * 60
_MANUAL_TTL_SECONDS = 60.0
# Si Turso falla, se cachea "vacio" un rato corto para no reintentar (varios segundos) en cada
# tecla; las sugerencias son opcionales, el formulario sigue funcionando a mano.
_FAILURE_TTL_SECONDS = 30.0

_PLACEHOLDER_TEXTS = frozenset({"", "-", "n.a"})
_PHONE_QUERY = re.compile(r"[\d\s+().-]+")


@dataclass(frozen=True)
class ClientSuggestion:
    name: str
    phone: str
    # Razon social / empresa: ayuda a distinguir homonimos en la lista, no se guarda en la incidencia.
    detail: str = ""


@dataclass(frozen=True)
class _Entry:
    suggestion: ClientSuggestion
    key: str
    name_norm: str
    haystack: str
    phone_digits: str


T = TypeVar("T")


class _Cached(Generic[T]):
    """Valor calculado una vez y reusado hasta que vence su TTL. El loader corre BAJO el lock:
    varios requests que llegan juntos con el cache frio esperan un unico calculo en vez de lanzar
    cada uno su propio (varios segundos) contra Turso."""

    def __init__(
        self, ttl: float, loader: Callable[[], T], fallback: T, failure_ttl: float = _FAILURE_TTL_SECONDS
    ) -> None:
        self._ttl = ttl
        self._loader = loader
        self._fallback = fallback
        self._failure_ttl = failure_ttl
        self._lock = threading.Lock()
        self._value: T | None = None
        self._expires_at = 0.0

    def is_fresh(self) -> bool:
        return self._value is not None and time.monotonic() < self._expires_at

    def get(self) -> T:
        with self._lock:
            now = time.monotonic()
            if self._value is not None and now < self._expires_at:
                return self._value
            try:
                self._value = self._loader()
                self._expires_at = time.monotonic() + self._ttl
            except Exception:
                logger.exception("No se pudieron cargar las sugerencias de incidencias")
                self._value = self._fallback
                self._expires_at = time.monotonic() + self._failure_ttl
            return self._value

    def invalidate(self) -> None:
        with self._lock:
            self._value = None
            self._expires_at = 0.0


def _normalize(text: str) -> str:
    """Sin tildes, sin mayusculas, espacios colapsados: "CAÑARI  Ore" == "canari ore"."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.casefold().split())


def _digits(text: str) -> str:
    return "".join(ch for ch in text if ch.isdigit())


def _text(value: object) -> str:
    """Texto limpio de una celda; los placeholders de C3 ("-", "N.A") cuentan como vacio."""
    if value is None:
        return ""
    cleaned = str(value).strip()
    return "" if cleaned.lower() in _PLACEHOLDER_TEXTS else cleaned


def _clean_phone(value: object) -> str:
    """Solo digitos cuando parece un telefono (9 a 13 digitos: 9 locales, 11 con el 51 del pais).
    Menos de 9 digitos es basura y se descarta; mas de 13 suele ser mas de un numero pegado y se
    deja tal cual (recortado al maximo del campo) en vez de inventar un corte."""
    text = _text(value)
    digits = _digits(text)
    if len(digits) < 9:
        return ""
    if len(digits) <= 13:
        return digits
    return text[:40]


def _entry_key(name_norm: str, phone_digits: str) -> str:
    # Mismo telefono con y sin el 51 del pais es el mismo cliente: se compara por los ultimos 9.
    return phone_digits[-9:] if phone_digits else f"nombre:{name_norm}"


def _build_entries(candidates: Iterable[ClientSuggestion]) -> list[_Entry]:
    """Fusiona candidatos del mismo cliente (mismo telefono, o mismo nombre si no hay telefono).
    Gana el primero en orden de llegada -- el caller los pasa de mas a menos confiable -- pero el
    nombre de los demas queda como alias de busqueda: alguien que escribio por WhatsApp como
    "Don Pepe" tambien se encuentra buscando "pepe" aunque el padron lo tenga con su nombre real."""
    merged: dict[str, tuple[ClientSuggestion, list[str]]] = {}
    for candidate in candidates:
        name_norm = _normalize(candidate.name)
        phone_digits = _digits(candidate.phone)
        if not name_norm and not phone_digits:
            continue
        key = _entry_key(name_norm, phone_digits)
        text = f"{name_norm} {_normalize(candidate.detail)}".strip()
        if key in merged:
            merged[key][1].append(text)
        else:
            merged[key] = (candidate, [text])
    return [
        _Entry(
            suggestion=suggestion,
            key=key,
            name_norm=_normalize(suggestion.name),
            haystack=" ".join(texts),
            phone_digits=_digits(suggestion.phone),
        )
        for key, (suggestion, texts) in merged.items()
    ]


def _load_c3_clients() -> list[_Entry]:
    conn = extraction_store.get_connection()
    try:
        roster = extraction_store.contacts_roster(conn)
        history = extraction_store.attention_client_counts(conn)
    finally:
        conn.close()

    candidates: list[ClientSuggestion] = []
    # Primero el padron (nombre formal), despues el historial (nombre de perfil de WhatsApp).
    for contact in roster:
        name = " ".join(
            part for part in (_text(contact["nombre"]), _text(contact["apellido"])) if part
        )
        name_norm = _normalize(name)
        detail = next(
            (
                value
                for value in (_text(contact["razon_social"]), _text(contact["empresa"]))
                if value and _normalize(value) != name_norm
            ),
            "",
        )
        candidates.append(ClientSuggestion(name, _clean_phone(contact["telefono"]), detail))
    for client in history:
        candidates.append(ClientSuggestion(_text(client["name"]), _clean_phone(client["phone"])))
    return _build_entries(candidates)


def _load_manual_clients() -> list[_Entry]:
    conn = incidents_store.get_connection()
    try:
        pairs = incidents_store.distinct_clients(conn)
    finally:
        conn.close()
    return _build_entries(
        ClientSuggestion(_text(cliente), _clean_phone(telefono)) for cliente, telefono in pairs
    )


def _load_c3_agents() -> dict[str, int]:
    conn = extraction_store.get_connection()
    try:
        return extraction_store.agent_case_counts(conn)
    finally:
        conn.close()


def _load_manual_agents() -> dict[str, int]:
    conn = incidents_store.get_connection()
    try:
        return incidents_store.agent_counts(conn)
    finally:
        conn.close()


_c3_clients: _Cached[list[_Entry]] = _Cached(_C3_TTL_SECONDS, _load_c3_clients, [])
_manual_clients: _Cached[list[_Entry]] = _Cached(_MANUAL_TTL_SECONDS, _load_manual_clients, [])
_c3_agents: _Cached[dict[str, int]] = _Cached(_C3_TTL_SECONDS, _load_c3_agents, {})
_manual_agents: _Cached[dict[str, int]] = _Cached(_MANUAL_TTL_SECONDS, _load_manual_agents, {})


def invalidate_manual() -> None:
    """Para llamar al crear/editar/borrar una incidencia: que lo recien escrito se sugiera ya."""
    _manual_clients.invalidate()
    _manual_agents.invalidate()


def reset_caches() -> None:
    """Solo para tests: el estado es global de proceso."""
    for cache in (_c3_clients, _manual_clients, _c3_agents, _manual_agents):
        cache.invalidate()


def warm_in_background() -> None:
    """Arma el indice de C3 en un hilo aparte: el formulario lo pide al abrirse para que la primera
    busqueda real no tenga que esperar varios segundos. Idempotente (el _Cached evita duplicar el
    calculo), asi que llamarlo de mas no cuesta nada."""
    if _c3_clients.is_fresh() and _c3_agents.is_fresh():
        return

    def _warm() -> None:
        _c3_clients.get()
        _c3_agents.get()

    threading.Thread(target=_warm, name="incident-lookups-warm", daemon=True).start()


def list_agents() -> list[str]:
    """Agentes conocidos (historial de C3 + escritos a mano), sin repetir el mismo nombre con
    distinta capitalizacion/tildes -- se muestra la grafia mas usada -- ordenados alfabeticamente."""
    spellings_by_name: dict[str, dict[str, int]] = {}
    for counts in (_c3_agents.get(), _manual_agents.get()):
        for agent, cases in counts.items():
            spellings = spellings_by_name.setdefault(_normalize(agent), {})
            spellings[agent] = spellings.get(agent, 0) + cases
    agents = [
        min(spellings.items(), key=lambda item: (-item[1], item[0]))[0]
        for spellings in spellings_by_name.values()
    ]
    return sorted(agents, key=lambda agent: (_normalize(agent), agent))


def is_searchable(query: str) -> bool:
    return _search_mode(query) is not None


def _search_mode(query: str) -> str | None:
    stripped = query.strip()
    if _PHONE_QUERY.fullmatch(stripped):
        return "phone" if len(_digits(stripped)) >= MIN_QUERY_DIGITS else None
    return "name" if len(_normalize(stripped)) >= MIN_QUERY_CHARS else None


def search_clients(query: str, limit: int = MAX_RESULTS) -> list[ClientSuggestion]:
    """Clientes que coinciden con `query`, como mucho `limit`. Una consulta solo de digitos
    (telefono, con o sin espacios/guiones/+) busca por telefono; cualquier otra busca por nombre,
    razon social o alias, exigiendo que aparezcan TODAS las palabras. Primero los que empiezan con
    lo escrito. Mismo cliente en varias fuentes se devuelve una sola vez (gana el padron/historial
    de C3 sobre lo escrito a mano)."""
    mode = _search_mode(query)
    if mode is None:
        return []

    if mode == "phone":
        digits = _digits(query)

        def match(entry: _Entry) -> bool:
            return digits in entry.phone_digits

        def rank(entry: _Entry) -> tuple:
            return (not entry.phone_digits.startswith(digits), entry.name_norm, entry.key)

    else:
        needle = _normalize(query)
        tokens = needle.split()

        def match(entry: _Entry) -> bool:
            return all(token in entry.haystack for token in tokens)

        def rank(entry: _Entry) -> tuple:
            return (not entry.name_norm.startswith(needle), entry.name_norm, entry.key)

    # Se deduplica ANTES de ordenar y con C3 primero: si el mismo cliente coincide en las dos
    # fuentes gana el dato de C3, sin importar como queden ordenados despues.
    unique: list[_Entry] = []
    seen: set[str] = set()
    for entry in (*_c3_clients.get(), *_manual_clients.get()):
        if entry.key in seen or not match(entry):
            continue
        seen.add(entry.key)
        unique.append(entry)
    unique.sort(key=rank)
    return [entry.suggestion for entry in unique[:limit]]
