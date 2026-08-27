import json
import threading
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


def _iso_datetime_expr(date_column: str, time_column: str) -> str:
    """DD/MM/YYYY + HH:MM:SS -> 'YYYY-MM-DD HH:MM:SS', mismo espiritu de guarda GLOB que
    _iso_date_expr (valores mal formados -> NULL en vez de una clave de orden corrupta). El
    resultado es directamente comparable con julianday() y con el "fecha || ' ' || hora" ya-ISO
    de transfer -- ver _since_key_expr."""
    date_glob = "[0-9][0-9]/[0-9][0-9]/[0-9][0-9][0-9][0-9]"
    time_glob = "[0-9][0-9]:[0-9][0-9]:[0-9][0-9]"
    iso_date = (
        f"substr({date_column}, 7, 4) || '-' || substr({date_column}, 4, 2) || '-' || "
        f"substr({date_column}, 1, 2)"
    )
    return (
        f"CASE WHEN {date_column} GLOB '{date_glob}' AND {time_column} GLOB '{time_glob}' "
        f"THEN {iso_date} || ' ' || {time_column} ELSE NULL END"
    )


def _norm_expr(column: str, empty_label: str, blank_values: tuple[str, ...] = ("",)) -> str:
    """Espeja las etiquetas de fallback agenteKey/campanaKey/estadoKeyOf del frontend
    (reports.functions.ts/atenciones.tsx): NULL o un valor "en blanco" (segun blank_values) se
    normaliza a empty_label antes de comparar/filtrar, para que un filtro como agente='Sin
    agente' calce con filas cuya columna esta vacia o es '-' en vez de literalmente esa etiqueta."""
    quoted_blanks = ", ".join(f"'{v}'" for v in blank_values)
    return (
        f"CASE WHEN {column} IS NULL OR TRIM({column}) IN ({quoted_blanks}) "
        f"THEN '{empty_label}' ELSE {column} END"
    )


_LIMA_OFFSET_SECONDS = 5 * 60 * 60


def _since_key_expr(table: str) -> str:
    """"Desde cuando esta con su agente actual" -- COALESCE del ultimo hop de transferencia
    (transfer.fecha ya es ISO, string-concat con hora ya es directamente comparable/ordenable,
    sin necesidad de parsear) con la hora de registro propia de la fila. NULL cuando no hay
    agente asignado (mismo criterio que withAgentSinceMs en reports.functions.ts: agenteKey ===
    'Sin agente' -> null), para que esas filas queden al final del orden sin importar timestamps.

    Usa lt.last_transfer_iso -- la columna pre-agregada por el LEFT JOIN que _branch_sql hace
    contra (SELECT id_atencion, MAX(fecha || ' ' || hora) FROM transfer GROUP BY id_atencion).
    Antes esto era una subconsulta correlacionada por fila (SELECT MAX(...) FROM transfer WHERE
    t.id_atencion = {table}.id_atencion), que se ejecutaba N veces (una por fila de atencion) en
    el COUNT y otra N en el SELECT paginado; el JOIN la resuelve una sola vez para toda la query."""
    agente_norm = _norm_expr("agente", "Sin agente", ("", "-"))
    start_iso = _iso_datetime_expr("fecha_registro", "hora_registro")
    return (
        f"CASE WHEN {agente_norm} = 'Sin agente' THEN NULL "
        f"ELSE COALESCE(lt.last_transfer_iso, {start_iso}) END"
    )


def _close_iso_expr() -> str:
    return _iso_datetime_expr("fecha_final", "hora_final")


def _elapsed_seconds_expr(since_key_col: str, close_iso_col: str) -> str:
    """Replica elapsedSeconds/withAgentSeconds (attention-records-table.tsx): si la atencion ya
    cerro, la duracion queda congelada en fecha_final/hora_final (ambos lados de la resta estan en
    la misma hora Lima "naive", el offset UTC-5 se cancela); si sigue abierta, se compara contra
    julianday('now') (UTC real), asi que ahi si hay que sumar el offset de vuelta."""
    return (
        f"CASE WHEN {close_iso_col} IS NOT NULL "
        f"THEN (julianday({close_iso_col}) - julianday({since_key_col})) * 86400.0 "
        f"ELSE (julianday('now') - julianday({since_key_col})) * 86400.0 - {_LIMA_OFFSET_SECONDS} END"
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
    hora_registro   TEXT,
    fecha_final     TEXT,
    hora_final      TEXT,
    numero_cliente  TEXT,
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    row_json        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attention_estado ON attention(estado);
CREATE INDEX IF NOT EXISTS idx_attention_campana ON attention(campana);
CREATE INDEX IF NOT EXISTS idx_attention_agente ON attention(agente);

CREATE TABLE IF NOT EXISTS outboundattention (
    id_atencion     TEXT PRIMARY KEY,
    estado          TEXT,
    agente          TEXT,
    campana         TEXT,
    fecha_registro  TEXT,
    hora_registro   TEXT,
    fecha_final     TEXT,
    hora_final      TEXT,
    numero_cliente  TEXT,
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    row_json        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outboundattention_estado ON outboundattention(estado);
CREATE INDEX IF NOT EXISTS idx_outboundattention_campana ON outboundattention(campana);
CREATE INDEX IF NOT EXISTS idx_outboundattention_agente ON outboundattention(agente);

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

CREATE TABLE IF NOT EXISTS benchmark_result (
    id_atencion             TEXT NOT NULL,
    direction               TEXT NOT NULL,
    agente                  TEXT,
    campana                 TEXT,
    estado                  TEXT,
    fecha_final             TEXT,
    hora_final              TEXT,
    cliente                 TEXT,
    first_response_seconds  REAL,
    has_greeting            INTEGER,
    has_farewell            INTEGER,
    quality_ok              INTEGER,
    llm_model               TEXT,
    llm_raw                 TEXT,
    llm_notes               TEXT,
    analyzed_at             TEXT,
    first_recorded_at       TEXT NOT NULL,
    last_updated_at         TEXT NOT NULL,
    row_json                TEXT NOT NULL,
    PRIMARY KEY (id_atencion, direction)
);
CREATE INDEX IF NOT EXISTS idx_benchmark_result_agente ON benchmark_result(agente);
CREATE INDEX IF NOT EXISTS idx_benchmark_result_analyzed_at ON benchmark_result(analyzed_at);
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
    "hora_registro": "Hora registro",
    "fecha_final": "Fecha final",
    "hora_final": "Hora final",
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


_ATTENTION_TABLES = ("attention", "outboundattention")
# hora_registro/hora_final no existian cuando attention/outboundattention se crearon por primera
# vez -- CREATE TABLE IF NOT EXISTS no las agrega a una tabla ya existente en el Turso en vivo, asi
# que _init_schema corre esta migracion aparte (PRAGMA table_info + ALTER TABLE por columna
# faltante). El valor crudo siempre estuvo en row_json (es la fila completa del XLSX ya parseada),
# asi que el backfill es gratis via json_extract -- no hace falta re-descargar nada.
_NEW_TIME_COLUMNS: dict[str, str] = {
    "hora_registro": "Hora registro",
    "hora_final": "Hora final",
}


def _existing_columns(conn: DBConnection, table: str) -> set[str]:
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def _migrate_time_columns(conn: DBConnection) -> None:
    for table in _ATTENTION_TABLES:
        existing = _existing_columns(conn, table)
        missing = [column for column in _NEW_TIME_COLUMNS if column not in existing]
        for column in missing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
        if missing:
            conn.commit()
        for column, source_header in _NEW_TIME_COLUMNS.items():
            conn.execute(
                f"UPDATE {table} SET {column} = json_extract(row_json, ?) WHERE {column} IS NULL",
                (f'$."{source_header}"',),
            )
        conn.commit()


# fecha_final/cliente no existian en benchmark_result cuando esa tabla se creo por primera
# vez -- mismo motivo/mismo patron que _migrate_time_columns arriba: CREATE TABLE IF NOT
# EXISTS no agrega columnas a una tabla ya existente en el Turso en vivo. El valor crudo
# siempre estuvo en row_json (la fila completa de attention/outboundattention que se
# benchmarkeo), asi que el backfill es gratis via json_extract.
_NEW_BENCHMARK_COLUMNS: dict[str, str] = {
    "fecha_final": "Fecha final",
    "hora_final": "Hora final",
    "cliente": "Nombre de cliente",
}


def _migrate_benchmark_result_columns(conn: DBConnection) -> None:
    existing = _existing_columns(conn, "benchmark_result")
    missing = [column for column in _NEW_BENCHMARK_COLUMNS if column not in existing]
    for column in missing:
        conn.execute(f"ALTER TABLE benchmark_result ADD COLUMN {column} TEXT")
    if missing:
        conn.commit()
    for column, source_header in _NEW_BENCHMARK_COLUMNS.items():
        conn.execute(
            "UPDATE benchmark_result SET "
            f"{column} = json_extract(row_json, ?) WHERE {column} IS NULL",
            (f'$."{source_header}"',),
        )
    conn.commit()
    # El indice sobre fecha_final vive aca (no en _SCHEMA) a proposito: si benchmark_result
    # ya existia sin esa columna, un CREATE INDEX en el mismo executescript() de _SCHEMA
    # fallaria (la columna todavia no existe en ese punto) -- crearlo aca garantiza que la
    # columna ya este presente (recien agregada arriba, o ya estaba en una tabla nueva).
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_benchmark_result_fecha_final_iso "
        f"ON benchmark_result ({_iso_date_expr('fecha_final')})"
    )
    conn.commit()


def _init_schema(conn: DBConnection) -> None:
    conn.executescript(_SCHEMA)
    _migrate_time_columns(conn)
    _migrate_benchmark_result_columns(conn)


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


def daily_counts(
    conn: DBConnection,
    report_name: str,
    date_from: str | None = None,
    date_to: str | None = None,
    agentes: list[str] | None = None,
) -> list[dict]:
    """Conteo de filas por dia de calendario, agregado en SQL (GROUP BY) en vez de traer cada
    row_json solo para contarlas del lado del caller -- pensado para graficos de tendencia
    ("casos por dia") que no necesitan el detalle fila por fila que history_rows() devuelve.
    Confirmado en vivo (2026-08-27) que history_rows() para un rango de 30 dias de "attention"
    transfiere ~3.8MB y tarda 8s+ (json.loads() por fila, tanto en el protocolo de
    turso_serverless como aca arriba en history_rows) -- GROUP BY server-side reduce eso a un
    puñado de filas (una por dia) sin ese costo. Solo cubre los reportes en _HISTORY_DATE_COLUMN
    (no "transfer": ver su comentario arriba sobre por que no se filtra/agrupa por dia).

    `agentes` filtra ANTES del GROUP BY (mismo patron de normalizacion "Sin agente" que
    _attention_where usa para /data/attention-records, incluido el mismo caso especial de
    lista vacia = "seleccion explicita de ningun agente" en vez de "sin filtro") -- pensado
    para excluir agentes especiales (bots/cuentas internas) del analisis de tendencias sin
    tener que caer al endpoint de detalle fila por fila."""
    date_column = _HISTORY_DATE_COLUMN[report_name]
    iso_expr = _iso_date_expr(date_column)
    clauses = [f"{iso_expr} IS NOT NULL"]
    params: list = []
    if date_from:
        clauses.append(f"{iso_expr} BETWEEN ? AND ?")
        params.append(date_from)
        params.append(date_to or date_from)
    if agentes is not None:
        if len(agentes) == 0:
            clauses.append("1=0")
        else:
            agente_norm = _norm_expr("agente", "Sin agente", ("", "-"))
            placeholders = ", ".join("?" for _ in agentes)
            clauses.append(f"{agente_norm} IN ({placeholders})")
            params.extend(agentes)
    where_sql = " AND ".join(clauses)
    cursor = conn.execute(
        f"SELECT {iso_expr} AS day, COUNT(*) FROM {report_name} WHERE {where_sql} "
        "GROUP BY day ORDER BY day",
        tuple(params),
    )
    return [{"date": day, "count": count} for day, count in cursor.fetchall()]


_STALE_THRESHOLD_SECONDS = 60 * 60  # espeja STALE_THRESHOLD_SECONDS en attention-records-table.tsx


@dataclass(frozen=True)
class AttentionRecordsPage:
    total: int
    stale_count: int
    rows: list[dict]  # row_json + {"direction": "incoming"|"outgoing"}
    transfers: list[dict]  # row_json de transfer, solo para los id_atencion de `rows`


def _attention_where(
    estados: list[str] | None,
    campana: str | None,
    agentes: list[str] | None,
    date_from: str | None,
    date_to: str | None,
) -> tuple[str, list]:
    clauses = ["1=1"]
    params: list = []
    if estados is not None:
        if len(estados) == 0:
            # Seleccion explicita de "ningun estado" -- distinto de "sin filtro" (estados=None).
            # El llamador (frontend) evita mandar esto por HTTP y corta antes de llegar aca, pero
            # esta guarda deja la funcion correcta igual si algo la llama directo con [].
            clauses.append("1=0")
        else:
            estado_norm = _norm_expr("estado", "Sin estado")
            placeholders = ", ".join("?" for _ in estados)
            clauses.append(f"{estado_norm} IN ({placeholders})")
            params.extend(estados)
    if campana and campana != "all":
        campana_norm = _norm_expr("campana", "Sin campaña")
        clauses.append(f"{campana_norm} = ?")
        params.append(campana)
    if agentes is not None:
        if len(agentes) == 0:
            # Mismo espiritu que la guarda de estados=[] arriba.
            clauses.append("1=0")
        else:
            agente_norm = _norm_expr("agente", "Sin agente", ("", "-"))
            placeholders = ", ".join("?" for _ in agentes)
            clauses.append(f"{agente_norm} IN ({placeholders})")
            params.extend(agentes)
    if date_from:
        iso_expr = _iso_date_expr("fecha_registro")
        clauses.append(f"{iso_expr} BETWEEN ? AND ?")
        params.append(date_from)
        params.append(date_to or date_from)
    return " AND ".join(clauses), params


_DIRECTION_TABLES: dict[str, list[tuple[str, str]]] = {
    "incoming": [("attention", "incoming")],
    "outgoing": [("outboundattention", "outgoing")],
    "all": [("attention", "incoming"), ("outboundattention", "outgoing")],
}


def _branch_sql(table: str, direction_label: str, where_sql: str) -> str:
    # LEFT JOIN contra el ultimo hop de transferencia pre-agregado por id_atencion,
    # en vez de una subconsulta correlacionada por fila (antes:
    # "(SELECT MAX(t.fecha || ' ' || t.hora) FROM transfer t WHERE t.id_atencion = {table}.id_atencion)").
    # Con miles de atenciones, esa subconsulta se ejecutaba una vez por fila en el
    # COUNT y otra en el SELECT paginado -- el LEFT JOIN la resuelve una sola vez.
    return (
        f"SELECT {table}.row_json, '{direction_label}' AS direction, {table}.id_atencion, "
        f"{_since_key_expr(table)} AS since_key, {_close_iso_expr()} AS close_iso "
        f"FROM {table} "
        f"LEFT JOIN (SELECT id_atencion, MAX(fecha || ' ' || hora) AS last_transfer_iso "
        f"FROM transfer GROUP BY id_atencion) lt "
        f"ON lt.id_atencion = {table}.id_atencion "
        f"WHERE {where_sql}"
    )


def attention_records_page(
    conn: DBConnection,
    *,
    direction: str = "all",
    estados: list[str] | None = None,
    campana: str | None = None,
    agentes: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> AttentionRecordsPage:
    branches = _DIRECTION_TABLES[direction]
    where_sql, where_params = _attention_where(estados, campana, agentes, date_from, date_to)
    inner_sql = " UNION ALL ".join(
        _branch_sql(table, label, where_sql) for table, label in branches
    )
    branch_params = tuple(where_params) * len(branches)

    count_sql = (
        "SELECT COUNT(*), SUM(CASE WHEN close_iso IS NULL AND since_key IS NOT NULL AND "
        f"((julianday('now') - julianday(since_key)) * 86400.0 - {_LIMA_OFFSET_SECONDS}) "
        f"> {_STALE_THRESHOLD_SECONDS} THEN 1 ELSE 0 END) FROM ({inner_sql})"
    )
    total_row = conn.execute(count_sql, branch_params).fetchone()
    total = total_row[0] or 0
    stale_count = total_row[1] or 0

    elapsed_expr = _elapsed_seconds_expr("since_key", "close_iso")
    page_sql = (
        f"SELECT row_json, direction, id_atencion FROM ({inner_sql}) "
        f"ORDER BY CASE WHEN since_key IS NULL THEN 1 ELSE 0 END, {elapsed_expr} DESC "
        "LIMIT ? OFFSET ?"
    )
    offset = (page - 1) * page_size
    cursor = conn.execute(page_sql, branch_params + (page_size, offset))

    rows = []
    ids = set()
    for row_json, direction_label, id_atencion in cursor.fetchall():
        record = json.loads(row_json)
        record["direction"] = direction_label
        rows.append(record)
        ids.add(str(id_atencion))

    return AttentionRecordsPage(
        total=total,
        stale_count=stale_count,
        rows=rows,
        transfers=_transfer_rows_for_ids(conn, ids),
    )


def _transfer_rows_for_ids(conn: DBConnection, ids: set[str]) -> list[dict]:
    if not ids:
        return []
    placeholders = ", ".join("?" for _ in ids)
    cursor = conn.execute(
        f"SELECT row_json FROM transfer WHERE id_atencion IN ({placeholders})",
        tuple(ids),
    )
    return [json.loads(row[0]) for row in cursor.fetchall()]


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


def closed_case_rows(
    conn: DBConnection,
    direction: str,
    *,
    estados: list[str],
    date_from: str | None = None,
) -> dict[str, dict]:
    """Casos de `direction` ('attention'|'outboundattention') cuyo estado normalizado esta
    en `estados`, opcionalmente acotado a los cerrados desde `date_from` (fecha ISO,
    comparada contra `fecha_final` -- el punto de esta consulta es "casos cerrados
    recientemente", no una ventana de fecha de registro; el matching contra el zip del
    reporte masivo es por ID, no depende de que este filtro coincida con lo que C3 filtre
    del otro lado). Devuelve {id_atencion: row_json ya parseado}."""
    if not estados:
        return {}
    table = direction
    estado_norm = _norm_expr("estado", "Sin estado")
    placeholders = ", ".join("?" for _ in estados)
    clauses = [f"{estado_norm} IN ({placeholders})"]
    params: list = list(estados)
    if date_from:
        iso_expr = _iso_date_expr("fecha_final")
        clauses.append(f"{iso_expr} >= ?")
        params.append(date_from)
    where_sql = " AND ".join(clauses)
    cursor = conn.execute(
        f"SELECT id_atencion, row_json FROM {table} WHERE {where_sql}", tuple(params)
    )
    return {
        str(id_atencion): json.loads(row_json)
        for id_atencion, row_json in cursor.fetchall()
    }


def already_benchmarked_ids(
    conn: DBConnection, direction: str, ids: list[str]
) -> set[str]:
    """IDs de `direction` que ya tienen un veredicto de calidad real (`has_greeting IS NOT
    NULL`) -- no basta con que la fila exista en benchmark_result: un caso cerrado sin PDF
    en el zip de hoy se registra igual (para no perder su tiempo de primera respuesta de los
    promedios por agente) pero sigue siendo candidato en la proxima corrida hasta que de
    verdad se le encuentre un PDF."""
    if not ids:
        return set()
    placeholders = ", ".join("?" for _ in ids)
    cursor = conn.execute(
        "SELECT id_atencion FROM benchmark_result WHERE direction = ? AND "
        f"id_atencion IN ({placeholders}) AND has_greeting IS NOT NULL",
        (direction, *ids),
    )
    return {str(row[0]) for row in cursor.fetchall()}


_BENCHMARK_ALL_COLUMNS = (
    "id_atencion",
    "direction",
    "agente",
    "campana",
    "estado",
    "fecha_final",
    "hora_final",
    "cliente",
    "first_response_seconds",
    "has_greeting",
    "has_farewell",
    "quality_ok",
    "llm_model",
    "llm_raw",
    "llm_notes",
    "analyzed_at",
    "first_recorded_at",
    "last_updated_at",
    "row_json",
)
# id_atencion/direction son la PK (no se actualizan); first_recorded_at se preserva del
# primer insert (mismo espiritu que first_seen_at en _upsert_by_pk) -- todo lo demas se
# sobreescribe con el valor de esta corrida.
_BENCHMARK_UPDATE_COLUMNS = (
    "agente",
    "campana",
    "estado",
    "fecha_final",
    "hora_final",
    "cliente",
    "first_response_seconds",
    "has_greeting",
    "has_farewell",
    "quality_ok",
    "llm_model",
    "llm_raw",
    "llm_notes",
    "analyzed_at",
    "last_updated_at",
    "row_json",
)


def _sql_bool(value: object) -> int | None:
    return None if value is None else int(bool(value))


def upsert_benchmark_results(
    conn: DBConnection, rows: list[dict], observed_at: str
) -> IngestResult:
    """Cada `row` en `rows` es un dict con keys: id_atencion, direction, agente, campana,
    estado, first_response_seconds, has_greeting (bool|None), has_farewell (bool|None),
    llm_model, llm_raw, llm_notes, row_json (dict -- la fila completa de
    attention/outboundattention, de donde se extraen `fecha_final`/`hora_final`/`cliente` para poder
    filtrar/mostrar sin tener que parsear row_json en el llamador -- `fecha_final` es la
    fecha REAL de cierre del caso, no cuando se corrio el analisis -- ver
    first_recorded_at/analyzed_at, que son fechas de proceso, no de negocio).
    `analyzed_at` se pone a `observed_at` solo cuando el caso trae un veredicto real
    (has_greeting is not None); si no, queda NULL -- asi already_benchmarked_ids lo sigue
    tratando como pendiente. El llamador NUNCA debe incluir aca un caso que
    already_benchmarked_ids ya haya marcado como analizado (evitaria pisar un veredicto
    real con uno vacio) -- ver pipeline.analyze_direction, que solo construye
    CaseBenchmark para los IDs pendientes, nunca para los ya benchmarkeados."""
    rows_skipped = 0
    valid_rows: list[tuple] = []
    for row in rows:
        id_atencion = _normalize_pk(row.get("id_atencion"))
        if id_atencion is None:
            rows_skipped += 1
            continue
        has_greeting = row.get("has_greeting")
        has_farewell = row.get("has_farewell")
        quality_ok = (
            has_greeting and has_farewell
            if has_greeting is not None and has_farewell is not None
            else None
        )
        analyzed_at = observed_at if has_greeting is not None else None
        row_json_dict = row.get("row_json") or {}
        fecha_final = row_json_dict.get("Fecha final")
        hora_final = row_json_dict.get("Hora final")
        cliente = row_json_dict.get("Nombre de cliente")
        valid_rows.append(
            (
                id_atencion,
                row["direction"],
                row.get("agente"),
                row.get("campana"),
                row.get("estado"),
                fecha_final,
                hora_final,
                cliente,
                row.get("first_response_seconds"),
                _sql_bool(has_greeting),
                _sql_bool(has_farewell),
                _sql_bool(quality_ok),
                row.get("llm_model"),
                row.get("llm_raw"),
                row.get("llm_notes"),
                analyzed_at,
                observed_at,
                observed_at,
                json.dumps(row_json_dict, default=str),
            )
        )

    if valid_rows:
        set_clause = ", ".join(f"{col}=excluded.{col}" for col in _BENCHMARK_UPDATE_COLUMNS)
        row_placeholder = "(" + ", ".join("?" for _ in _BENCHMARK_ALL_COLUMNS) + ")"
        for batch in _chunked(valid_rows, _BATCH_SIZE):
            sql = (
                f"INSERT INTO benchmark_result ({', '.join(_BENCHMARK_ALL_COLUMNS)}) "
                f"VALUES {', '.join([row_placeholder] * len(batch))} "
                f"ON CONFLICT(id_atencion, direction) DO UPDATE SET {set_clause}"
            )
            params = tuple(value for row_values in batch for value in row_values)
            conn.execute(sql, params)
        conn.commit()

    return IngestResult(
        report_name="benchmark_result",
        rows_seen=len(rows),
        rows_upserted=len(valid_rows),
        rows_skipped=rows_skipped,
    )


_BENCHMARK_RESULT_COLUMNS = (
    "id_atencion",
    "direction",
    "agente",
    "campana",
    "estado",
    "fecha_final",
    "hora_final",
    "cliente",
    "first_response_seconds",
    "has_greeting",
    "has_farewell",
    "quality_ok",
    "llm_notes",
    "analyzed_at",
)


def benchmark_result_rows(
    conn: DBConnection,
    *,
    direction: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """Lista plana para el frontend -- mismo espiritu que history_rows(), pero devolviendo
    columnas ya tipadas (no row_json) porque el frontend agrega sobre estos campos
    directamente, no sobre el xlsx crudo. El filtro de fecha es sobre `fecha_final` (cuando
    el CASO se cerro de verdad, igual que "terminadas" en /atenciones) -- NO sobre
    first_recorded_at/analyzed_at (que son fechas de cuando corrio el analisis, no fechas
    de negocio; un caso cerrado ayer analizado hoy no debe aparecer al filtrar "hoy")."""
    clauses = ["1=1"]
    params: list = []
    if direction:
        clauses.append("direction = ?")
        params.append(direction)
    if date_from:
        iso_expr = _iso_date_expr("fecha_final")
        clauses.append(f"{iso_expr} BETWEEN ? AND ?")
        params.append(date_from)
        params.append(date_to or date_from)
    where_sql = " AND ".join(clauses)
    order_expr = _iso_datetime_expr("fecha_final", "hora_final")
    cursor = conn.execute(
        f"SELECT {', '.join(_BENCHMARK_RESULT_COLUMNS)} FROM benchmark_result "
        f"WHERE {where_sql} ORDER BY {order_expr} DESC, id_atencion",
        tuple(params),
    )
    rows = []
    for record in cursor.fetchall():
        row = dict(zip(_BENCHMARK_RESULT_COLUMNS, record))
        # bool(0/1) por nombre de columna, no por indice posicional -- evita tener que
        # recalcular numeros a mano cada vez que _BENCHMARK_RESULT_COLUMNS cambia de orden
        # o largo (ya paso dos veces).
        for bool_column in ("has_greeting", "has_farewell", "quality_ok"):
            row[bool_column] = None if row[bool_column] is None else bool(row[bool_column])
        rows.append(row)
    return rows
