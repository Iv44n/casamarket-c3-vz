import threading
from dataclasses import dataclass
from typing import Literal, Protocol

import turso_serverless

from .. import config

# Los 5 proveedores que build_provider() (llm/__init__.py) sabe construir -- vive aca, no
# alla, porque LLMSettingsRequest (routers/benchmarks.py) tambien necesita validar contra
# esta lista antes de guardar, y llm/__init__.py ya importa `settings` (para el type hint de
# LLMConfig), asi que el import inverso crearia un ciclo.
LLMProviderName = Literal["minimax", "deepseek", "openai", "gemini", "claude"]
LLM_PROVIDER_NAMES: tuple[LLMProviderName, ...] = (
    "minimax",
    "deepseek",
    "openai",
    "gemini",
    "claude",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_settings (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    provider_name     TEXT NOT NULL,
    api_key           TEXT,
    model             TEXT,
    base_url          TEXT,
    updated_at        TEXT NOT NULL
);
"""

# Nombres de columna de cuando esta tabla solo conocia un proveedor (MiniMax) -- ver
# _migrate_generic_columns.
_LEGACY_COLUMNS = ("minimax_api_key", "minimax_model", "minimax_base_url")
_GENERIC_COLUMNS = ("api_key", "model", "base_url")


class DBConnection(Protocol):
    """Mismo contrato minimo que auth/store.py's y extraction/store.py's DBConnection."""

    def execute(self, sql: str, parameters: tuple = ()): ...
    def executescript(self, sql: str): ...
    def commit(self) -> None: ...


@dataclass(frozen=True)
class LLMConfig:
    """Config generica: los mismos 3 campos (api_key/model/base_url) sirven para los 5
    proveedores -- 4 hablan el formato de API que popularizo OpenAI (MiniMax, DeepSeek,
    ChatGPT/OpenAI, Gemini via su capa de compatibilidad; ver llm/__init__.py) y solo
    difieren en que base_url/modelo usan por default, asi que ninguno necesita su propia
    clase de proveedor -- reusan OpenAIProvider. El quinto (Claude) si tiene su propio SDK/
    forma de API (anthropic_provider.py), pero comparte la misma forma de credenciales
    (api_key + model), asi que no hace falta un campo extra para el.

    `base_url=None` para un proveedor OpenAI-compatible usa el default fijo de ese proveedor
    (ver llm/__init__.py's _OPENAI_COMPATIBLE_DEFAULTS) -- solo hace falta llenarlo a mano
    para pisar ese default (por ejemplo, apuntar "minimax" a OpenRouter en vez de la API
    oficial de MiniMax). Claude lo ignora del todo, la Anthropic API no lo necesita aca.

    Antes vivia en app/config.py, leida de LLM_PROVIDER/MINIMAX_* como variables de entorno --
    ahora la configuran los admins desde el panel (PUT /benchmarks/settings), persistida aca
    en Turso, para no depender de un redeploy para cambiar de proveedor/modelo/rotar la api
    key."""

    provider_name: str
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None
    updated_at: str | None = None


_schema_initialized = False
_schema_lock = threading.Lock()


def get_connection() -> turso_serverless.Connection:
    global _schema_initialized
    turso_config = config.load_turso_config()
    conn = turso_serverless.connect(
        turso_config.database_url, auth_token=turso_config.auth_token
    )
    if not _schema_initialized:
        with _schema_lock:
            if not _schema_initialized:
                _init_schema(conn)
                _migrate_generic_columns(conn)
                _schema_initialized = True
    return conn


def _init_schema(conn: DBConnection) -> None:
    conn.executescript(_SCHEMA)


def _existing_columns(conn: DBConnection, table: str) -> set[str]:
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def _migrate_generic_columns(conn: DBConnection) -> None:
    """Una sola vez: agrega api_key/model/base_url si esta tabla es de antes de soportar
    multiples proveedores (solo tenia minimax_api_key/minimax_model/minimax_base_url) y
    copia lo que ya estaba guardado -- asi un admin que ya habia configurado MiniMax no
    pierde su config al desplegar este cambio. Aditivo nada mas (ALTER TABLE ADD COLUMN,
    nunca RENAME/DROP), mismo criterio que extraction/store.py's
    _migrate_benchmark_result_quality_columns -- las columnas minimax_* quedan sin uso
    despues de esto, no se borran (mas simple y sin riesgo en una tabla Turso remota).
    Una tabla NUEVA (creada ya con `_SCHEMA` de arriba) nunca tiene columnas minimax_*, asi
    que el backfill de mas abajo es un no-op para ella."""
    existing = _existing_columns(conn, "llm_settings")
    missing = [c for c in _GENERIC_COLUMNS if c not in existing]
    for column in missing:
        conn.execute(f"ALTER TABLE llm_settings ADD COLUMN {column} TEXT")
    if missing:
        conn.commit()

    if all(c in existing for c in _LEGACY_COLUMNS):
        conn.execute(
            "UPDATE llm_settings SET "
            "api_key = COALESCE(api_key, minimax_api_key), "
            "model = COALESCE(model, minimax_model), "
            "base_url = COALESCE(base_url, minimax_base_url) "
            "WHERE id = 1"
        )
        conn.commit()


def load_llm_config(conn: DBConnection) -> LLMConfig | None:
    """None cuando ningun admin configuro esto todavia (fila unica ausente) -- distinto de
    una LLMConfig con campos vacios, para que el caller (pipeline.run_benchmark_cycle) pueda
    dar un mensaje claro de "todavia no se configuro" en vez de un ValueError generico de
    build_provider() sobre campos faltantes."""
    cursor = conn.execute(
        "SELECT provider_name, api_key, model, base_url, updated_at "
        "FROM llm_settings WHERE id = 1"
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return LLMConfig(
        provider_name=row[0],
        api_key=row[1],
        model=row[2],
        base_url=row[3],
        updated_at=row[4],
    )


def save_llm_config(
    conn: DBConnection,
    provider_name: str,
    api_key: str | None,
    model: str | None,
    base_url: str | None,
    updated_at: str,
) -> LLMConfig:
    """`api_key=None` preserva la api key ya guardada (no la pisa con NULL) -- para que un
    admin pueda ajustar el proveedor/modelo/base_url sin tener que reingresar el secreto
    cada vez. Para efectivamente borrar la key habria que guardar un string vacio, no None."""
    if api_key is None:
        existing = load_llm_config(conn)
        api_key = existing.api_key if existing else None

    conn.execute(
        "INSERT INTO llm_settings (id, provider_name, api_key, model, base_url, updated_at) "
        "VALUES (1, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET provider_name=excluded.provider_name, "
        "api_key=excluded.api_key, model=excluded.model, base_url=excluded.base_url, "
        "updated_at=excluded.updated_at",
        (provider_name, api_key, model, base_url, updated_at),
    )
    conn.commit()
    saved = load_llm_config(conn)
    assert saved is not None
    return saved
