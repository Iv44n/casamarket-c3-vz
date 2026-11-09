"""Incidencias registradas a mano desde el panel (no vienen de C3) y el catalogo de valores
para clasificarlas (origen/tipo/ambito/resultado).

Mismo patron self-contained que auth/store.py y benchmarks/settings.py: su propio
get_connection() con schema lazy sobre la misma Turso, dominio separado de extraction/ (que
solo se lee para sembrar el catalogo, via extraction.store.distinct_incident_values)."""

import threading
from dataclasses import dataclass
from typing import Protocol

import turso_serverless

from .. import config

CATEGORIES = ("origen", "tipo", "ambito", "resultado")
# resultado es opcional: una incidencia se puede registrar antes de saber como termino.
REQUIRED_CATEGORIES = ("origen", "tipo", "ambito")

SOURCE_C3 = "c3"
SOURCE_MANUAL = "manual"

# Tope del listado por rango de fechas -- la carga manual se espera en decenas/pocos cientos de
# filas por dia (no los miles de las atenciones de C3), asi que no hay paginacion server-side;
# si se pasa del tope, la respuesta lo dice (truncated) en vez de cortar en silencio.
LIST_LIMIT = 2000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS manual_incident (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha        TEXT NOT NULL,
    hora         TEXT NOT NULL DEFAULT '',
    cliente      TEXT NOT NULL DEFAULT '',
    telefono     TEXT NOT NULL DEFAULT '',
    agente       TEXT NOT NULL DEFAULT '',
    origen       TEXT NOT NULL,
    tipo         TEXT NOT NULL,
    ambito       TEXT NOT NULL,
    resultado    TEXT NOT NULL DEFAULT '',
    descripcion  TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_by   TEXT,
    updated_at   TEXT,
    deleted_by   TEXT,
    deleted_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_manual_incident_fecha ON manual_incident(fecha);

CREATE TABLE IF NOT EXISTS incident_catalog_option (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL CHECK (category IN ('origen', 'tipo', 'ambito', 'resultado')),
    value       TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 1,
    source      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    UNIQUE (category, value)
);
"""

_INCIDENT_COLUMNS = (
    "id, fecha, hora, cliente, telefono, agente, origen, tipo, ambito, resultado, descripcion, "
    "created_by, created_at, updated_by, updated_at"
)
_OPTION_COLUMNS = "id, category, value, active, source, created_at"


class DBConnection(Protocol):
    def execute(self, sql: str, parameters: tuple = ()): ...
    def executescript(self, sql: str): ...
    def commit(self) -> None: ...


@dataclass(frozen=True)
class IncidentInput:
    fecha: str
    hora: str
    cliente: str
    telefono: str
    agente: str
    origen: str
    tipo: str
    ambito: str
    resultado: str
    descripcion: str


@dataclass(frozen=True)
class ManualIncident:
    id: int
    fecha: str
    hora: str
    cliente: str
    telefono: str
    agente: str
    origen: str
    tipo: str
    ambito: str
    resultado: str
    descripcion: str
    created_by: str
    created_at: str
    updated_by: str | None
    updated_at: str | None


@dataclass(frozen=True)
class CatalogOption:
    id: int
    category: str
    value: str
    active: bool
    source: str
    created_at: str


class InvalidCatalogValueError(ValueError):
    def __init__(self, category: str, value: str) -> None:
        self.category = category
        self.value = value
        if value:
            message = f"{category}: {value!r} no es una opcion activa del catalogo"
        else:
            message = f"{category} es obligatorio"
        super().__init__(message)


class CatalogOptionExistsError(Exception):
    pass


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


def _row_to_incident(row) -> ManualIncident:
    return ManualIncident(*row)


def _row_to_option(row) -> CatalogOption:
    return CatalogOption(
        id=row[0],
        category=row[1],
        value=row[2],
        active=bool(row[3]),
        source=row[4],
        created_at=row[5],
    )


# --- Catalogo -------------------------------------------------------------------------------


def list_catalog(conn: DBConnection) -> list[CatalogOption]:
    cursor = conn.execute(
        f"SELECT {_OPTION_COLUMNS} FROM incident_catalog_option ORDER BY category, value"
    )
    return [_row_to_option(row) for row in cursor.fetchall()]


def get_catalog_option(conn: DBConnection, option_id: int) -> CatalogOption | None:
    cursor = conn.execute(
        f"SELECT {_OPTION_COLUMNS} FROM incident_catalog_option WHERE id = ?", (option_id,)
    )
    row = cursor.fetchone()
    return None if row is None else _row_to_option(row)


def _active_values(conn: DBConnection) -> dict[str, set[str]]:
    cursor = conn.execute(
        "SELECT category, value FROM incident_catalog_option WHERE active = 1"
    )
    active: dict[str, set[str]] = {category: set() for category in CATEGORIES}
    for category, value in cursor.fetchall():
        active.setdefault(category, set()).add(value)
    return active


def add_catalog_option(
    conn: DBConnection, category: str, value: str, created_at: str, source: str = SOURCE_MANUAL
) -> CatalogOption:
    if category not in CATEGORIES:
        raise ValueError(f"Categoria invalida: {category!r}")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("El valor no puede estar vacio")
    # Check-then-insert (mismo criterio que auth/store.create_user): no depende de la clase
    # exacta de IntegrityError que levante turso_serverless.
    existing = conn.execute(
        "SELECT id FROM incident_catalog_option WHERE category = ? AND value = ?",
        (category, cleaned),
    ).fetchone()
    if existing is not None:
        raise CatalogOptionExistsError(f"{category}: {cleaned!r} ya existe en el catalogo")
    cursor = conn.execute(
        "INSERT INTO incident_catalog_option (category, value, active, source, created_at) "
        "VALUES (?, ?, 1, ?, ?)",
        (category, cleaned, source, created_at),
    )
    conn.commit()
    option = get_catalog_option(conn, cursor.lastrowid)
    assert option is not None
    return option


def set_catalog_option_active(
    conn: DBConnection, option_id: int, active: bool
) -> CatalogOption | None:
    conn.execute(
        "UPDATE incident_catalog_option SET active = ? WHERE id = ?", (int(active), option_id)
    )
    conn.commit()
    return get_catalog_option(conn, option_id)


def import_catalog_values(
    conn: DBConnection, values_by_category: dict[str, list[str]], created_at: str
) -> int:
    """Agrega (source='c3') los valores que todavia no estan en el catalogo. Idempotente, y
    NUNCA reactiva una opcion que un admin desactivo: INSERT OR IGNORE no toca filas que ya
    existen. Devuelve cuantas opciones nuevas se agregaron."""
    before = conn.execute("SELECT COUNT(*) FROM incident_catalog_option").fetchone()[0]
    rows: list[tuple] = []
    for category, values in values_by_category.items():
        if category not in CATEGORIES:
            continue
        for value in values:
            cleaned = value.strip()
            if cleaned:
                rows.append((category, cleaned, SOURCE_C3, created_at))
    # Un INSERT multi-VALUES por lote en vez de un execute() por fila -- turso_serverless paga
    # un round-trip por execute() (ver extraction/store.py's _BATCH_SIZE). ~130 valores hoy.
    for start in range(0, len(rows), 200):
        batch = rows[start : start + 200]
        placeholders = ", ".join(["(?, ?, 1, ?, ?)"] * len(batch))
        conn.execute(
            "INSERT OR IGNORE INTO incident_catalog_option "
            f"(category, value, active, source, created_at) VALUES {placeholders}",
            tuple(item for row in batch for item in row),
        )
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM incident_catalog_option").fetchone()[0]
    return after - before


# --- Incidencias ----------------------------------------------------------------------------


def _validate_catalog_values(
    conn: DBConnection, data: IncidentInput, previous: ManualIncident | None
) -> None:
    """Cada categoria debe ser una opcion ACTIVA del catalogo. Excepcion: al editar, el valor que
    la incidencia ya tenia sigue valiendo aunque un admin lo haya desactivado despues -- si no,
    no se podria corregir la descripcion de una incidencia vieja sin reclasificarla."""
    active = _active_values(conn)
    for category in CATEGORIES:
        value = getattr(data, category)
        if not value:
            if category in REQUIRED_CATEGORIES:
                raise InvalidCatalogValueError(category, value)
            continue
        if value in active.get(category, set()):
            continue
        if previous is not None and getattr(previous, category) == value:
            continue
        raise InvalidCatalogValueError(category, value)


def list_incidents(
    conn: DBConnection, date_from: str, date_to: str, limit: int = LIST_LIMIT
) -> tuple[list[ManualIncident], bool]:
    """Incidencias no borradas con fecha en [date_from, date_to] (ISO, inclusive), mas
    recientes primero. Devuelve (filas, truncated)."""
    cursor = conn.execute(
        f"SELECT {_INCIDENT_COLUMNS} FROM manual_incident "
        "WHERE deleted_at IS NULL AND fecha BETWEEN ? AND ? "
        "ORDER BY fecha DESC, hora DESC, id DESC LIMIT ?",
        (date_from, date_to, limit + 1),
    )
    rows = [_row_to_incident(row) for row in cursor.fetchall()]
    return rows[:limit], len(rows) > limit


def get_incident(conn: DBConnection, incident_id: int) -> ManualIncident | None:
    cursor = conn.execute(
        f"SELECT {_INCIDENT_COLUMNS} FROM manual_incident WHERE id = ? AND deleted_at IS NULL",
        (incident_id,),
    )
    row = cursor.fetchone()
    return None if row is None else _row_to_incident(row)


def create_incident(
    conn: DBConnection, data: IncidentInput, username: str, now: str
) -> ManualIncident:
    _validate_catalog_values(conn, data, previous=None)
    cursor = conn.execute(
        "INSERT INTO manual_incident (fecha, hora, cliente, telefono, agente, origen, tipo, "
        "ambito, resultado, descripcion, created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            data.fecha,
            data.hora,
            data.cliente,
            data.telefono,
            data.agente,
            data.origen,
            data.tipo,
            data.ambito,
            data.resultado,
            data.descripcion,
            username,
            now,
        ),
    )
    conn.commit()
    incident = get_incident(conn, cursor.lastrowid)
    assert incident is not None
    return incident


def update_incident(
    conn: DBConnection, incident_id: int, data: IncidentInput, username: str, now: str
) -> ManualIncident | None:
    previous = get_incident(conn, incident_id)
    if previous is None:
        return None
    _validate_catalog_values(conn, data, previous=previous)
    conn.execute(
        "UPDATE manual_incident SET fecha = ?, hora = ?, cliente = ?, telefono = ?, agente = ?, "
        "origen = ?, tipo = ?, ambito = ?, resultado = ?, descripcion = ?, updated_by = ?, "
        "updated_at = ? WHERE id = ? AND deleted_at IS NULL",
        (
            data.fecha,
            data.hora,
            data.cliente,
            data.telefono,
            data.agente,
            data.origen,
            data.tipo,
            data.ambito,
            data.resultado,
            data.descripcion,
            username,
            now,
            incident_id,
        ),
    )
    conn.commit()
    return get_incident(conn, incident_id)


def delete_incident(conn: DBConnection, incident_id: int, username: str, now: str) -> bool:
    """Borrado logico: cualquier cuenta con acceso a incidencias puede borrar las de otros, asi
    que la fila queda recuperable desde la DB (deleted_by/deleted_at) en vez de desaparecer.
    False si no existe o ya estaba borrada."""
    if get_incident(conn, incident_id) is None:
        return False
    conn.execute(
        "UPDATE manual_incident SET deleted_by = ?, deleted_at = ? "
        "WHERE id = ? AND deleted_at IS NULL",
        (username, now, incident_id),
    )
    conn.commit()
    return True


# --- Valores ya registrados a mano (para sugerir en el formulario) --------------------------


def distinct_clients(conn: DBConnection) -> list[tuple[str, str]]:
    """Pares (cliente, telefono) distintos de las incidencias no borradas, sin los vacios."""
    cursor = conn.execute(
        "SELECT DISTINCT cliente, telefono FROM manual_incident "
        "WHERE deleted_at IS NULL AND (cliente != '' OR telefono != '')"
    )
    return [(cliente, telefono) for cliente, telefono in cursor.fetchall()]


def agent_counts(conn: DBConnection) -> dict[str, int]:
    """Agentes escritos a mano en incidencias no borradas, con cuantas incidencias tiene cada uno."""
    cursor = conn.execute(
        "SELECT agente, COUNT(*) FROM manual_incident "
        "WHERE deleted_at IS NULL AND agente != '' GROUP BY agente"
    )
    return {agente: cases for agente, cases in cursor.fetchall()}
