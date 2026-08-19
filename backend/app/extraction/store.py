import json
from dataclasses import dataclass, field
from typing import Protocol

import turso_serverless

from .. import config

# Reportes cuya columna de fecha de negocio se guarda como texto "DD/MM/YYYY" (extraccion
# directa del XLSX, ver _upsert_by_pk). "transfer" queda afuera a proposito: su columna "fecha"
# se guarda ya en ISO "YYYY-MM-DD" (formato distinto, confirmado corriendo un chequeo de datos en
# vivo contra la Turso real) y de todos modos nunca se filtra por fecha en el llamador (transfer
# se correlaciona por "Atención ID", no por dia -- filtrarlo podria descartar en silencio
# transferencias registradas justo despues de medianoche respecto a su atencion padre).
_HISTORY_DATE_COLUMN: dict[str, str] = {
    "attention": "fecha_registro",
    "outboundattention": "fecha_registro",
    "callincoming": "fecha",
    "calloutgoing": "fecha",
}


def _iso_date_expr(column: str) -> str:
    """DD/MM/YYYY -> YYYY-MM-DD, con guarda contra valores mal formados. Un substr()/|| sin
    guarda produciria silenciosamente una clave de orden incorrecta para cualquier otro string
    de 10 caracteres (p.ej. un valor ya-ISO) -- GLOB descarta eso antes de intentar convertir.
    Entrada que no calza -> NULL -> excluida de cualquier BETWEEN, igual que toIsoDate() en el
    frontend hace hoy con fechas mal formadas. CREATE INDEX y WHERE deben usar EXACTAMENTE esta
    misma expresion: el query planner de SQLite compara expression indexes de forma textual,
    no algebraica."""
    glob_pattern = "[0-9][0-9]/[0-9][0-9]/[0-9][0-9][0-9][0-9]"
    return (
        f"CASE WHEN {column} GLOB '{glob_pattern}' "
        f"THEN substr({column}, 7, 4) || '-' || substr({column}, 4, 2) || '-' || substr({column}, 1, 2) "
        f"ELSE NULL END"
    )


_DATE_RANGE_INDEXES = "\n".join(
    f"CREATE INDEX IF NOT EXISTS idx_{table}_{column}_iso ON {table} ({_iso_date_expr(column)});"
    for table, column in _HISTORY_DATE_COLUMN.items()
)

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS attention (
    id_atencion     TEXT PRIMARY KEY,
    estado          TEXT,
    agente          TEXT,
    campana         TEXT,
    fecha_registro  TEXT,
    fecha_final     TEXT,
    numero_cliente  TEXT,
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    row_json        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attention_estado ON attention(estado);
CREATE INDEX IF NOT EXISTS idx_attention_campana ON attention(campana);

CREATE TABLE IF NOT EXISTS outboundattention (
    id_atencion     TEXT PRIMARY KEY,
    estado          TEXT,
    agente          TEXT,
    campana         TEXT,
    fecha_registro  TEXT,
    fecha_final     TEXT,
    numero_cliente  TEXT,
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    row_json        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outboundattention_estado ON outboundattention(estado);
CREATE INDEX IF NOT EXISTS idx_outboundattention_campana ON outboundattention(campana);

CREATE TABLE IF NOT EXISTS callincoming (
    linkedid        TEXT PRIMARY KEY,
    estado          TEXT,
    agente          TEXT,
    campana         TEXT,
    fecha           TEXT,
    numero_cliente  TEXT,
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    row_json        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_callincoming_estado ON callincoming(estado);
CREATE INDEX IF NOT EXISTS idx_callincoming_campana ON callincoming(campana);

CREATE TABLE IF NOT EXISTS calloutgoing (
    linkedid        TEXT PRIMARY KEY,
    estado          TEXT,
    agente          TEXT,
    campana         TEXT,
    fecha           TEXT,
    numero_cliente  TEXT,
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    row_json        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_calloutgoing_estado ON calloutgoing(estado);
CREATE INDEX IF NOT EXISTS idx_calloutgoing_campana ON calloutgoing(campana);

CREATE TABLE IF NOT EXISTS transfer (
    id_atencion     TEXT NOT NULL,
    fecha           TEXT NOT NULL,
    hora            TEXT NOT NULL,
    agente_origen   TEXT NOT NULL DEFAULT '',
    destino         TEXT NOT NULL DEFAULT '',
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    row_json        TEXT NOT NULL,
    PRIMARY KEY (id_atencion, fecha, hora, agente_origen, destino)
);
CREATE INDEX IF NOT EXISTS idx_transfer_id_atencion ON transfer(id_atencion);

CREATE TABLE IF NOT EXISTS contacts_snapshot (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at   TEXT NOT NULL,
    doc_number    TEXT,
    telefono      TEXT,
    empresa       TEXT,
    row_json      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_contacts_snapshot_captured_at ON contacts_snapshot(captured_at);

CREATE TABLE IF NOT EXISTS sync_status (
    kind         TEXT PRIMARY KEY,
    status_json  TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
{_DATE_RANGE_INDEXES}
"""


class DBConnection(Protocol):
    """Cualquier conexion DB-API 2.0 compatible con sqlite3 (stdlib sqlite3.Connection
    en tests, turso_serverless.Connection en produccion) -- store.py no distingue."""

    def execute(self, sql: str, parameters: tuple = ()): ...
    def executescript(self, sql: str): ...
    def commit(self) -> None: ...


@dataclass(frozen=True)
class TableSpec:
    table: str
    pk_column: str
    pk_field: str
    extracted: dict[str, str] = field(default_factory=dict)


_ATTENTION_EXTRACTED = {
    "estado": "Estado",
    "agente": "Agente",
    "campana": "Campaña",
    "fecha_registro": "Fecha registro",
    "fecha_final": "Fecha final",
    "numero_cliente": "Número cliente",
}
_CALL_EXTRACTED = {
    "estado": "Estado",
    "agente": "Agente",
    "campana": "Campaña",
    "fecha": "Fecha",
    "numero_cliente": "Nº Cliente",
}

REPORT_TABLE_SPECS: dict[str, TableSpec] = {
    "attention": TableSpec("attention", "id_atencion", "ID atención", _ATTENTION_EXTRACTED),
    "outboundattention": TableSpec(
        "outboundattention", "id_atencion", "ID atención", _ATTENTION_EXTRACTED
    ),
    "callincoming": TableSpec("callincoming", "linkedid", "Linkedid", _CALL_EXTRACTED),
    "calloutgoing": TableSpec("calloutgoing", "linkedid", "Linkedid", _CALL_EXTRACTED),
}


@dataclass(frozen=True)
class IngestResult:
    report_name: str
    rows_seen: int
    rows_upserted: int
    rows_skipped: int


_schema_initialized = False


def get_connection() -> turso_serverless.Connection:
    global _schema_initialized
    turso_config = config.load_turso_config()
    conn = turso_serverless.connect(
        turso_config.database_url, auth_token=turso_config.auth_token
    )
    if not _schema_initialized:
        _init_schema(conn)
        _schema_initialized = True
    return conn


def _init_schema(conn: DBConnection) -> None:
    conn.executescript(_SCHEMA)


def _normalize_pk(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, float):
        value = int(value) if value.is_integer() else value
    text = str(value).strip()
    return text or None


# turso_serverless (0.1.0) hace un round-trip de red POR CADA execute()/executemany()
# item -- confirmado en vivo (~0.44s/fila, ~500 filas => mas de 3 minutos). Empaquetar
# muchas filas en un solo INSERT ... VALUES (...), (...), ... reduce eso a un puñado de
# round-trips (mismas ~500 filas en ~1.5s). El tamaño del batch es conservador para no
# arriesgar un statement/URL demasiado largo sobre HTTP.
_BATCH_SIZE = 200


def _chunked(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def upsert_report_rows(
    conn: DBConnection, report_name: str, rows: list[dict], observed_at: str
) -> IngestResult:
    if report_name == "transfer":
        return _upsert_transfer_rows(conn, rows, observed_at)
    spec = REPORT_TABLE_SPECS[report_name]
    return _upsert_by_pk(conn, spec, rows, observed_at)


def _upsert_by_pk(
    conn: DBConnection, spec: TableSpec, rows: list[dict], observed_at: str
) -> IngestResult:
    extracted_cols = list(spec.extracted)
    pk_column = spec.pk_column
    all_columns = [pk_column, *extracted_cols, "first_seen_at", "last_seen_at", "row_json"]
    update_cols = [*extracted_cols, "last_seen_at", "row_json"]

    by_pk: dict[str, tuple] = {}
    rows_skipped = 0
    for row in rows:
        pk = _normalize_pk(row.get(spec.pk_field))
        if pk is None:
            rows_skipped += 1
            continue
        values = [pk] + [row.get(source_key) for source_key in spec.extracted.values()]
        values += [observed_at, observed_at, json.dumps(row, default=str)]
        by_pk[pk] = tuple(values)  # dedupe: la ultima ocurrencia de un mismo PK gana

    valid_rows = list(by_pk.values())
    if valid_rows:
        set_clause = ", ".join(f"{col}=excluded.{col}" for col in update_cols)
        row_placeholder = "(" + ", ".join("?" for _ in all_columns) + ")"
        for batch in _chunked(valid_rows, _BATCH_SIZE):
            sql = (
                f"INSERT INTO {spec.table} ({', '.join(all_columns)}) "
                f"VALUES {', '.join([row_placeholder] * len(batch))} "
                f"ON CONFLICT({pk_column}) DO UPDATE SET {set_clause}"
            )
            params = tuple(value for row_values in batch for value in row_values)
            conn.execute(sql, params)
        conn.commit()

    return IngestResult(
        report_name=spec.table,
        rows_seen=len(rows),
        rows_upserted=len(valid_rows),
        rows_skipped=rows_skipped,
    )


_TRANSFER_COLUMNS = (
    "id_atencion",
    "fecha",
    "hora",
    "agente_origen",
    "destino",
    "first_seen_at",
    "last_seen_at",
    "row_json",
)


def _upsert_transfer_rows(
    conn: DBConnection, rows: list[dict], observed_at: str
) -> IngestResult:
    by_key: dict[tuple, tuple] = {}
    rows_skipped = 0
    for row in rows:
        id_atencion = _normalize_pk(row.get("Atención ID"))
        fecha = row.get("Fecha")
        hora = row.get("Hora")
        if id_atencion is None or not fecha or not hora:
            rows_skipped += 1
            continue
        agente_origen = str(row.get("Agente Origen") or "")
        destino = str(row.get("Destino") or "")
        key = (id_atencion, str(fecha), str(hora), agente_origen, destino)
        by_key[key] = (
            *key,
            observed_at,
            observed_at,
            json.dumps(row, default=str),
        )

    valid_rows = list(by_key.values())
    if valid_rows:
        row_placeholder = "(" + ", ".join("?" for _ in _TRANSFER_COLUMNS) + ")"
        for batch in _chunked(valid_rows, _BATCH_SIZE):
            sql = (
                f"INSERT INTO transfer ({', '.join(_TRANSFER_COLUMNS)}) "
                f"VALUES {', '.join([row_placeholder] * len(batch))} "
                "ON CONFLICT(id_atencion, fecha, hora, agente_origen, destino) DO UPDATE SET "
                "last_seen_at=excluded.last_seen_at, row_json=excluded.row_json"
            )
            params = tuple(value for row_values in batch for value in row_values)
            conn.execute(sql, params)
        conn.commit()

    return IngestResult(
        report_name="transfer",
        rows_seen=len(rows),
        rows_upserted=len(valid_rows),
        rows_skipped=rows_skipped,
    )


def insert_contacts_snapshot(conn: DBConnection, rows: list[dict], captured_at: str) -> IngestResult:
    all_rows = [
        (
            captured_at,
            row.get("Número de documento"),
            row.get("Telefono"),
            row.get("Empresa"),
            json.dumps(row, default=str),
        )
        for row in rows
    ]
    row_placeholder = "(?, ?, ?, ?, ?)"
    for batch in _chunked(all_rows, _BATCH_SIZE):
        sql = (
            "INSERT INTO contacts_snapshot (captured_at, doc_number, telefono, empresa, row_json) "
            f"VALUES {', '.join([row_placeholder] * len(batch))}"
        )
        params = tuple(value for row_values in batch for value in row_values)
        conn.execute(sql, params)
    if all_rows:
        conn.commit()
    return IngestResult(
        report_name="contacts",
        rows_seen=len(rows),
        rows_upserted=len(all_rows),
        rows_skipped=0,
    )


_HISTORY_ORDER: dict[str, str] = {
    "attention": "first_seen_at, id_atencion",
    "outboundattention": "first_seen_at, id_atencion",
    "callincoming": "first_seen_at, linkedid",
    "calloutgoing": "first_seen_at, linkedid",
    "transfer": "first_seen_at, id_atencion, fecha, hora",
}


def history_rows(
    conn: DBConnection,
    report_name: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict] | None:
    table = report_name
    order_by = _HISTORY_ORDER[report_name]
    date_column = _HISTORY_DATE_COLUMN.get(report_name)
    if date_from is None or date_column is None:
        cursor = conn.execute(f"SELECT row_json FROM {table} ORDER BY {order_by}")
    else:
        iso_expr = _iso_date_expr(date_column)
        cursor = conn.execute(
            f"SELECT row_json FROM {table} WHERE {iso_expr} BETWEEN ? AND ? ORDER BY {order_by}",
            (date_from, date_to or date_from),
        )
    rows = [json.loads(row[0]) for row in cursor.fetchall()]
    return rows or None


def save_sync_status(
    conn: DBConnection, kind: str, status: dict, updated_at: str
) -> None:
    conn.execute(
        "INSERT INTO sync_status (kind, status_json, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(kind) DO UPDATE SET "
        "status_json=excluded.status_json, updated_at=excluded.updated_at",
        (kind, json.dumps(status, default=str), updated_at),
    )
    conn.commit()


def load_sync_status(conn: DBConnection, kind: str) -> dict | None:
    cursor = conn.execute(
        "SELECT status_json FROM sync_status WHERE kind = ?", (kind,)
    )
    row = cursor.fetchone()
    return json.loads(row[0]) if row is not None else None
