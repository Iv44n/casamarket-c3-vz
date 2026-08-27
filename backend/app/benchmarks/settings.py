import threading
from dataclasses import dataclass
from typing import Protocol

import turso_serverless

from .. import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_settings (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    provider_name     TEXT NOT NULL,
    minimax_api_key   TEXT,
    minimax_model     TEXT,
    minimax_base_url  TEXT,
    updated_at        TEXT NOT NULL
);
"""


class DBConnection(Protocol):
    """Mismo contrato minimo que auth/store.py's y extraction/store.py's DBConnection."""

    def execute(self, sql: str, parameters: tuple = ()): ...
    def executescript(self, sql: str): ...
    def commit(self) -> None: ...


@dataclass(frozen=True)
class LLMConfig:
    """Config agnostica de proveedor: `provider_name` decide que campos importan. Agregar un
    proveedor nuevo es agregar sus propios campos aca + una rama nueva en
    benchmarks/llm/build_provider(), sin tocar los de los proveedores ya existentes. Hoy solo
    esta configurado MiniMax -- su API es compatible con la de OpenAI, asi que no necesita una
    clase de proveedor propia: reusa OpenAIProvider tal cual, solo con su propio api_key/model/
    base_url.

    Antes vivia en app/config.py, leida de LLM_PROVIDER/MINIMAX_* como variables de entorno --
    ahora la configuran los admins desde el panel (PUT /benchmarks/settings), persistida aca en
    Turso, para no depender de un redeploy para cambiar de modelo/rotar la api key."""

    provider_name: str
    minimax_api_key: str | None = None
    minimax_model: str | None = None
    minimax_base_url: str | None = None
    updated_at: str | None = None

    @property
    def model_label(self) -> str | None:
        """Nombre de modelo a guardar en benchmark_result.llm_model para auditoria --
        generico sobre el proveedor, para que pipeline.py no necesite conocer los campos
        propios de cada uno."""
        if self.provider_name == "minimax":
            return self.minimax_model
        return None


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
                _schema_initialized = True
    return conn


def _init_schema(conn: DBConnection) -> None:
    conn.executescript(_SCHEMA)


def load_llm_config(conn: DBConnection) -> LLMConfig | None:
    """None cuando ningun admin configuro esto todavia (fila unica ausente) -- distinto de una
    LLMConfig con campos vacios, para que el caller (pipeline.run_benchmark_cycle) pueda dar un
    mensaje claro de "todavia no se configuro" en vez de un ValueError generico de
    build_provider() sobre campos faltantes."""
    cursor = conn.execute(
        "SELECT provider_name, minimax_api_key, minimax_model, minimax_base_url, updated_at "
        "FROM llm_settings WHERE id = 1"
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return LLMConfig(
        provider_name=row[0],
        minimax_api_key=row[1],
        minimax_model=row[2],
        minimax_base_url=row[3],
        updated_at=row[4],
    )


def save_llm_config(
    conn: DBConnection,
    provider_name: str,
    minimax_api_key: str | None,
    minimax_model: str | None,
    minimax_base_url: str | None,
    updated_at: str,
) -> LLMConfig:
    """`minimax_api_key=None` preserva la api key ya guardada (no la pisa con NULL) -- para que
    un admin pueda ajustar el modelo o la base_url sin tener que reingresar el secreto cada vez.
    Para efectivamente borrar la key habria que guardar un string vacio, no None."""
    if minimax_api_key is None:
        existing = load_llm_config(conn)
        minimax_api_key = existing.minimax_api_key if existing else None

    conn.execute(
        "INSERT INTO llm_settings (id, provider_name, minimax_api_key, minimax_model, "
        "minimax_base_url, updated_at) VALUES (1, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET provider_name=excluded.provider_name, "
        "minimax_api_key=excluded.minimax_api_key, minimax_model=excluded.minimax_model, "
        "minimax_base_url=excluded.minimax_base_url, updated_at=excluded.updated_at",
        (provider_name, minimax_api_key, minimax_model, minimax_base_url, updated_at),
    )
    conn.commit()
    saved = load_llm_config(conn)
    assert saved is not None
    return saved
