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
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                  INTEGER,
    id_atencion             TEXT NOT NULL,
    direction               TEXT NOT NULL,
    agente                  TEXT,
    campana                 TEXT,
    estado                  TEXT,
    fecha_final             TEXT,
    hora_final              TEXT,
    cliente                 TEXT,
    first_response_seconds  REAL,
    greeting_level          TEXT,
    has_farewell            INTEGER,
    complexity              TEXT,
    handled_well_for_complexity INTEGER,
    spelling_ok             INTEGER,
    had_transfer            INTEGER,
    transferred_from_agents TEXT,
    informed_transfer       INTEGER,
    quality_ok              INTEGER,
    llm_model               TEXT,
    llm_raw                 TEXT,
    llm_notes               TEXT,
    analyzed_at             TEXT,
    first_recorded_at       TEXT NOT NULL,
    last_updated_at         TEXT NOT NULL,
    row_json                TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_benchmark_result_agente ON benchmark_result(agente);
CREATE INDEX IF NOT EXISTS idx_benchmark_result_analyzed_at ON benchmark_result(analyzed_at);
CREATE INDEX IF NOT EXISTS idx_benchmark_result_case ON benchmark_result(id_atencion, direction);
-- idx_benchmark_result_run_id NO va aca a proposito -- mismo motivo que
-- idx_benchmark_result_fecha_final_iso mas abajo: si benchmark_result ya existia sin esa
-- columna (Turso vieja, pre-versionado), este CREATE INDEX en el mismo executescript()
-- fallaria con "no such column: run_id" antes de que _migrate_benchmark_result_versioning
-- tenga chance de agregarla. Se crea en _init_schema(), despues de esa migracion.

CREATE TABLE IF NOT EXISTS benchmark_run (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    ok              INTEGER,
    date_from       TEXT,
    date_to         TEXT,
    force_reanalyze INTEGER NOT NULL DEFAULT 0,
    directions      TEXT NOT NULL,
    summary_json    TEXT,
    error           TEXT
);
CREATE INDEX IF NOT EXISTS idx_benchmark_run_started_at ON benchmark_run(started_at);
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


def _migrate_benchmark_result_versioning(conn: DBConnection) -> None:
    """benchmark_result tenia PRIMARY KEY (id_atencion, direction) -- upsert, una fila por caso,
    pisada en cada corrida de benchmarks. Ahora cada corrida agrega su propia fila (run_id la
    liga a benchmark_run), para poder ver como cambio el veredicto de un mismo caso entre
    corridas en vez de perder el anterior. SQLite no soporta alterar una PRIMARY KEY in-place,
    asi que esto reconstruye la tabla entera -- RENAME (no DROP) la vieja a una tabla de
    respaldo en vez de borrarla, para que una falla a mitad de camino nunca deje un estado sin
    ningun dato recuperable (confirmado en vivo con turso_serverless: ALTER TABLE RENAME
    preserva la numeracion de sqlite_sequence de la tabla, asi que el AUTOINCREMENT nuevo no
    colisiona con nada). Corre una sola vez por DB (gateada por si run_id ya existe -- una Turso
    nueva ya crea benchmark_result con este shape via _SCHEMA y no-opea de una); la tabla de
    respaldo (benchmark_result_pre_versioning) se puede borrar a mano mas adelante, una vez
    confirmada la migracion en produccion."""
    existing = _existing_columns(conn, "benchmark_result")
    if "run_id" in existing:
        return
    conn.executescript(
        """
        BEGIN;
        ALTER TABLE benchmark_result RENAME TO benchmark_result_pre_versioning;
        CREATE TABLE benchmark_result (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id                  INTEGER,
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
            row_json                TEXT NOT NULL
        );
        INSERT INTO benchmark_result (
            run_id, id_atencion, direction, agente, campana, estado, fecha_final, hora_final,
            cliente, first_response_seconds, has_greeting, has_farewell, quality_ok, llm_model,
            llm_raw, llm_notes, analyzed_at, first_recorded_at, last_updated_at, row_json
        )
        SELECT
            NULL, id_atencion, direction, agente, campana, estado, fecha_final, hora_final,
            cliente, first_response_seconds, has_greeting, has_farewell, quality_ok, llm_model,
            llm_raw, llm_notes, analyzed_at, first_recorded_at, last_updated_at, row_json
        FROM benchmark_result_pre_versioning;
        CREATE INDEX IF NOT EXISTS idx_benchmark_result_agente ON benchmark_result(agente);
        CREATE INDEX IF NOT EXISTS idx_benchmark_result_analyzed_at ON benchmark_result(analyzed_at);
        CREATE INDEX IF NOT EXISTS idx_benchmark_result_case ON benchmark_result(id_atencion, direction);
        CREATE INDEX IF NOT EXISTS idx_benchmark_result_run_id ON benchmark_result(run_id);
        COMMIT;
        """
    )
    # El indice sobre fecha_final vive aca, no en el executescript de arriba, mismo motivo que
    # _migrate_benchmark_result_columns: es una expresion sobre la columna, mas prolijo crearlo
    # despues de que la tabla nueva ya este confirmada.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_benchmark_result_fecha_final_iso "
        f"ON benchmark_result ({_iso_date_expr('fecha_final')})"
    )
    conn.commit()


# complexity/handled_well_for_complexity/had_transfer/informed_transfer/greeting_level/
# spelling_ok/transferred_from_agents no existian en benchmark_result antes de que se
# agregaran sus respectivas evaluaciones -- mismo patron aditivo que
# _migrate_benchmark_result_columns (ALTER TABLE ADD COLUMN, no un rebuild -- a diferencia de
# _migrate_benchmark_result_versioning, esto no toca la PK). greeting_level reemplaza a la
# vieja columna has_greeting (booleana) -- has_greeting sigue existiendo fisicamente en una
# Turso ya migrada (no se dropea, evita otro rebuild de PK) pero deja de leerse/escribirse
# desde aca en adelante; ver already_benchmarked_ids sobre por que su marcador de "ya juzgado"
# no depende de esta columna puntual.
_NEW_BENCHMARK_QUALITY_COLUMNS: dict[str, str] = {
    "complexity": "TEXT",
    "handled_well_for_complexity": "INTEGER",
    "had_transfer": "INTEGER",
    "informed_transfer": "INTEGER",
    "greeting_level": "TEXT",
    "spelling_ok": "INTEGER",
    "transferred_from_agents": "TEXT",
}


def _migrate_benchmark_result_quality_columns(conn: DBConnection) -> None:
    existing = _existing_columns(conn, "benchmark_result")
    missing = [c for c in _NEW_BENCHMARK_QUALITY_COLUMNS if c not in existing]
    for column in missing:
        conn.execute(
            f"ALTER TABLE benchmark_result ADD COLUMN {column} "
            f"{_NEW_BENCHMARK_QUALITY_COLUMNS[column]}"
        )
    if missing:
        conn.commit()
    # had_transfer, a diferencia de informed_transfer, no es un juicio del LLM -- es un hecho
    # verificable ahora mismo contra la tabla transfer, sin importar cuando corrio el analisis
    # que grabo la fila. Las filas grabadas ANTES de que esta columna existiera quedan en NULL
    # tras el ALTER TABLE de arriba; sin este backfill, BenchmarkCaseResult.had_transfer (bool,
    # no-nullable) rompe /benchmarks/results con un ResponseValidationError para cada fila
    # vieja (confirmado en vivo el 2026-08-28). informed_transfer sigue en NULL para esas filas
    # a proposito -- eso si de verdad no se puede saber sin haberle preguntado al LLM.
    conn.execute(
        "UPDATE benchmark_result SET had_transfer = 1 WHERE had_transfer IS NULL "
        "AND id_atencion IN (SELECT DISTINCT id_atencion FROM transfer)"
    )
    conn.execute("UPDATE benchmark_result SET had_transfer = 0 WHERE had_transfer IS NULL")
    conn.commit()
    # transferred_from_agents -- mismo espiritu que el backfill de had_transfer arriba: es un
    # hecho reconstruible ahora mismo contra `transfer`, no un juicio del LLM, asi que se
    # backfillea de una en vez de dejarlo en NULL para siempre en filas viejas. No se puede
    # hacer con un UPDATE ... WHERE IN (...) generico como had_transfer (cada caso necesita su
    # propia lista, no un valor fijo) -- pero SI hace falta un UPDATE por LOTE, no uno por id:
    # turso_serverless hace un round-trip HTTP por cada conn.execute(), asi que un UPDATE
    # individual por id_atencion (con potencialmente cientos de casos pendientes en la Turso
    # real) volvia esta migracion -- que corre en CUALQUIER get_connection(), incluida
    # extraction/state.py's _hydrate_once() detras de GET /extraction/status -- en un colgado
    # de varios minutos (confirmado en vivo el 2026-08-31 con faulthandler.dump_traceback_later,
    # bloqueado en turso_serverless.session._post/ssl.do_handshake). Un solo UPDATE con CASE
    # por lote logra lo mismo (valor distinto por fila) en un unico round-trip.
    pending_ids = [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT id_atencion FROM benchmark_result "
            "WHERE transferred_from_agents IS NULL"
        ).fetchall()
    ]
    for batch in _chunked(pending_ids, _BATCH_SIZE):
        origins = transfer_origin_agents_for_cases(conn, batch)
        case_sql = " ".join("WHEN ? THEN ?" for _ in batch)
        case_params = [
            value for id_atencion in batch for value in (id_atencion, json.dumps(origins.get(id_atencion, [])))
        ]
        placeholders = ", ".join("?" for _ in batch)
        conn.execute(
            f"UPDATE benchmark_result SET transferred_from_agents = CASE id_atencion {case_sql} END "
            f"WHERE id_atencion IN ({placeholders}) AND transferred_from_agents IS NULL",
            tuple(case_params) + tuple(batch),
        )
    if pending_ids:
        conn.commit()


def _init_schema(conn: DBConnection) -> None:
    conn.executescript(_SCHEMA)
    _migrate_time_columns(conn)
    _migrate_benchmark_result_columns(conn)
    _migrate_benchmark_result_versioning(conn)
    _migrate_benchmark_result_quality_columns(conn)
    # run_id esta garantizado presente aca (recien creado por _SCHEMA, o agregado por la
    # migracion de arriba) -- ver el comentario junto a benchmark_result en _SCHEMA sobre por
    # que este indice no puede vivir ahi.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_benchmark_result_run_id ON benchmark_result(run_id)")
    conn.commit()


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
    date_to: str | None = None,
) -> dict[str, dict]:
    """Casos de `direction` ('attention'|'outboundattention') cuyo estado normalizado esta
    en `estados`, opcionalmente acotado a los cerrados desde `date_from` (fecha ISO,
    comparada contra `fecha_final` -- el punto de esta consulta es "casos cerrados
    recientemente", no una ventana de fecha de registro; el matching contra el zip del
    reporte masivo es por ID, no depende de que este filtro coincida con lo que C3 filtre
    del otro lado). `date_to` es opcional aun con `date_from` presente -- sin el, el rango
    queda abierto hacia adelante (`fecha_final >= date_from`), IGUAL que el comportamiento de
    siempre; no uses el idiom `date_to or date_from` en el caller si lo que queres es ese
    default abierto (eso lo convertiria en un solo dia). Devuelve {id_atencion: row_json ya
    parseado}."""
    if not estados:
        return {}
    table = direction
    estado_norm = _norm_expr("estado", "Sin estado")
    placeholders = ", ".join("?" for _ in estados)
    clauses = [f"{estado_norm} IN ({placeholders})"]
    params: list = list(estados)
    if date_from:
        iso_expr = _iso_date_expr("fecha_final")
        if date_to:
            clauses.append(f"{iso_expr} BETWEEN ? AND ?")
            params.append(date_from)
            params.append(date_to)
        else:
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


def _execute_retrying(conn: DBConnection, sql: str, params: tuple = ()):
    """conn.execute() reintentado UNA vez si turso_serverless levanta OperationalError.

    turso_serverless mantiene un stream HTTP con estado (un "baton") por conexion; si esa
    conexion queda inactiva demasiado tiempo, Turso lo expira server-side y la siguiente
    query falla con OperationalError("HTTP status 404: stream not found: ...") -- confirmado
    en vivo el 2026-08-28, disparado por el loop de polling de analyze_direction esperando el
    reporte masivo de C3 (hasta config.BENCHMARK_MASSIVE_TIMEOUT_SECONDS = 6h) con `conn`
    ociosa mientras tanto. turso_serverless resetea su baton local en cualquier falla de
    transporte (session.Session._reset_stream()), asi que la proxima llamada abre un stream
    nuevo sola -- ver el docstring de _post() en esa libreria: "the driver never re-sends a
    request on its own; whether re-running a failed statement is safe is the application's
    call". Es seguro reintentar aca: "stream not found" significa que el servidor nunca
    encontro el stream para ejecutar el statement, o sea que no se aplico nada la primera vez.

    Deliberadamente envuelve la llamada a conn.execute() en si, no toda una funcion que haga
    varias -- ver record_benchmark_results, donde reintentar la funcion completa duplicaria
    los batches que ya se habian insertado antes del que fallo."""
    try:
        return conn.execute(sql, params)
    except turso_serverless.OperationalError:
        return conn.execute(sql, params)


def already_benchmarked_ids(
    conn: DBConnection, direction: str, ids: list[str]
) -> set[str]:
    """IDs de `direction` que ya tienen un veredicto de calidad real (`analyzed_at IS NOT
    NULL`) -- no basta con que la fila exista en benchmark_result: un caso cerrado sin PDF
    en el zip de hoy se registra igual (para no perder su tiempo de primera respuesta de los
    promedios por agente) pero sigue siendo candidato en la proxima corrida hasta que de
    verdad se le encuentre un PDF.

    Usa `analyzed_at`, no una columna de criterio puntual (antes `has_greeting`, hoy
    `greeting_level`) -- `analyzed_at` significa exactamente "hubo un juicio real del LLM"
    (ver record_benchmark_results) sin importar que criterios existian cuando se grabo esa
    fila. Si esto dependiera de `greeting_level IS NOT NULL`, las filas grabadas ANTES de que
    esa columna existiera (con `greeting_level` NULL por ser viejas, no por no haber sido
    juzgadas) se verian como "todavia pendientes" y se re-analizarian solas en la proxima
    corrida normal -- gasto de LLM no pedido, ademas de inconsistente con como
    complexity/handled_well_for_complexity NO dispararon un re-analisis automatico de casos
    viejos cuando se agregaron."""
    if not ids:
        return set()
    placeholders = ", ".join("?" for _ in ids)
    cursor = _execute_retrying(
        conn,
        "SELECT id_atencion FROM benchmark_result WHERE direction = ? AND "
        f"id_atencion IN ({placeholders}) AND analyzed_at IS NOT NULL",
        (direction, *ids),
    )
    return {str(row[0]) for row in cursor.fetchall()}


def transfer_origin_agents_for_cases(
    conn: DBConnection, ids: list[str]
) -> dict[str, list[str]]:
    """Para cada id de `ids` que tuvo al menos una transferencia, la lista de agentes_origen de
    TODOS sus saltos (un caso puede pasar por mas de un agente antes de llegar al que figura
    como `agente` en la fila -- ese es siempre el agente FINAL, el que cerro el caso), en orden
    cronologico y sin deduplicar (si un caso volvio dos veces al mismo agente, eso es
    informacion real). IDs sin ninguna transferencia simplemente no aparecen como key -- el
    llamador usa `.get(id, [])`, y esa ausencia/presencia de key es tambien como se determina
    `had_transfer` (ver pipeline.build_case_benchmarks), sin necesitar una consulta aparte solo
    para eso. Se consulta ANTES de armar el prompt del LLM (pipeline.analyze_direction) --
    justo despues del polling largo de massive.run_direction() -- ver _execute_retrying. No
    filtra por direction -- transfer no distingue attention/outboundattention, se correlaciona
    solo por id_atencion (ver _upsert_transfer_rows)."""
    if not ids:
        return {}
    placeholders = ", ".join("?" for _ in ids)
    cursor = _execute_retrying(
        conn,
        "SELECT id_atencion, agente_origen FROM transfer "
        f"WHERE id_atencion IN ({placeholders}) ORDER BY id_atencion, fecha, hora",
        tuple(ids),
    )
    origins: dict[str, list[str]] = {}
    for id_atencion, agente_origen in cursor.fetchall():
        origins.setdefault(str(id_atencion), []).append(agente_origen)
    return origins


_BENCHMARK_ALL_COLUMNS = (
    "run_id",
    "id_atencion",
    "direction",
    "agente",
    "campana",
    "estado",
    "fecha_final",
    "hora_final",
    "cliente",
    "first_response_seconds",
    "greeting_level",
    "has_farewell",
    "complexity",
    "handled_well_for_complexity",
    "spelling_ok",
    "had_transfer",
    "transferred_from_agents",
    "informed_transfer",
    "quality_ok",
    "llm_model",
    "llm_raw",
    "llm_notes",
    "analyzed_at",
    "first_recorded_at",
    "last_updated_at",
    "row_json",
)


def _sql_bool(value: object) -> int | None:
    return None if value is None else int(bool(value))


def record_benchmark_results(
    conn: DBConnection, rows: list[dict], observed_at: str, *, run_id: int | None = None
) -> IngestResult:
    """Cada `row` en `rows` es un dict con keys: id_atencion, direction, agente, campana,
    estado, first_response_seconds, greeting_level (str|None, "ninguno"/"casual"/"formal"),
    has_farewell (bool|None), complexity (str|None, "baja"/"media"/"alta"),
    handled_well_for_complexity (bool|None), spelling_ok (bool|None), had_transfer (bool --
    hecho, nunca None, ver transfer_origin_agents_for_cases), transferred_from_agents
    (list[str] -- hecho, nunca None (lista vacia si no hubo transferencia), los agentes_origen
    de TODOS los saltos que tuvo el caso antes de llegar al `agente` final que ya muestra la
    fila -- se guarda como JSON), informed_transfer (bool|None -- None cuando had_transfer es
    False, no aplica), llm_model, llm_raw, llm_notes, row_json (dict -- la fila completa de
    attention/outboundattention, de donde se extraen
    `fecha_final`/`hora_final`/`cliente` para poder filtrar/mostrar sin tener que parsear
    row_json en el llamador -- `fecha_final` es la fecha REAL de cierre del caso, no cuando se
    corrio el analisis -- ver first_recorded_at/analyzed_at, que son fechas de proceso, no de
    negocio).
    `analyzed_at` se pone a `observed_at` solo cuando el caso trae un veredicto real
    (greeting_level is not None -- se pregunta en cada corrida, mismo rol que cumplia
    has_greeting antes); si no, queda NULL -- asi already_benchmarked_ids lo sigue tratando
    como pendiente. `quality_ok` combina "hubo saludo, casual o formal"/has_farewell/
    handled_well_for_complexity/spelling_ok siempre, y ademas informed_transfer SOLO cuando
    had_transfer es True (un caso sin transferencia no debe fallar el veredicto general por un
    criterio que no le aplica) -- None si falta cualquiera de los criterios que sí aplican.

    Siempre hace INSERT (nunca UPDATE) -- benchmark_result ya no tiene una PK sobre
    (id_atencion, direction), asi que una corrida posterior del mismo caso agrega una fila
    nueva en vez de pisar la anterior (trazabilidad entre corridas via `run_id`, ver
    benchmark_run). `first_recorded_at`/`last_updated_at` quedan iguales entre si en cada fila
    (ya no hay "actualizacion" cuyo primer valor preservar). `benchmark_result_rows()` es quien
    decide cual fila mostrar quiere el ultimo veredicto por caso -- esta funcion no dedupea."""
    rows_skipped = 0
    valid_rows: list[tuple] = []
    for row in rows:
        id_atencion = _normalize_pk(row.get("id_atencion"))
        if id_atencion is None:
            rows_skipped += 1
            continue
        greeting_level = row.get("greeting_level")
        greeting_ok = (
            greeting_level in ("casual", "formal") if greeting_level is not None else None
        )
        has_farewell = row.get("has_farewell")
        handled_well_for_complexity = row.get("handled_well_for_complexity")
        spelling_ok = row.get("spelling_ok")
        had_transfer = bool(row.get("had_transfer"))
        informed_transfer = row.get("informed_transfer")
        quality_criteria = [greeting_ok, has_farewell, handled_well_for_complexity, spelling_ok]
        if had_transfer:
            quality_criteria.append(informed_transfer)
        quality_ok = (
            all(quality_criteria) if all(c is not None for c in quality_criteria) else None
        )
        analyzed_at = observed_at if greeting_level is not None else None
        row_json_dict = row.get("row_json") or {}
        fecha_final = row_json_dict.get("Fecha final")
        hora_final = row_json_dict.get("Hora final")
        cliente = row_json_dict.get("Nombre de cliente")
        valid_rows.append(
            (
                run_id,
                id_atencion,
                row["direction"],
                row.get("agente"),
                row.get("campana"),
                row.get("estado"),
                fecha_final,
                hora_final,
                cliente,
                row.get("first_response_seconds"),
                greeting_level,
                _sql_bool(has_farewell),
                row.get("complexity"),
                _sql_bool(handled_well_for_complexity),
                _sql_bool(spelling_ok),
                _sql_bool(had_transfer),
                json.dumps(row.get("transferred_from_agents") or []),
                _sql_bool(informed_transfer),
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
        row_placeholder = "(" + ", ".join("?" for _ in _BENCHMARK_ALL_COLUMNS) + ")"
        for batch in _chunked(valid_rows, _BATCH_SIZE):
            sql = (
                f"INSERT INTO benchmark_result ({', '.join(_BENCHMARK_ALL_COLUMNS)}) "
                f"VALUES {', '.join([row_placeholder] * len(batch))}"
            )
            params = tuple(value for row_values in batch for value in row_values)
            # _execute_retrying, no conn.execute() liso -- esta funcion corre justo despues
            # del loop de juicios del LLM en analyze_direction (que puede tardar bastante con
            # muchos casos concurrentes), mismo riesgo de stream expirado que
            # transfer_origin_agents_for_cases. Reintentar SOLO este batch (no la funcion
            # entera) evita duplicar un batch anterior que ya se haya insertado bien.
            _execute_retrying(conn, sql, params)
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
    "greeting_level",
    "has_farewell",
    "complexity",
    "handled_well_for_complexity",
    "spelling_ok",
    "had_transfer",
    "transferred_from_agents",
    "informed_transfer",
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
    de negocio; un caso cerrado ayer analizado hoy no debe aparecer al filtrar "hoy").

    Desde que benchmark_result puede tener mas de una fila por (id_atencion, direction)
    (una por corrida, ver record_benchmark_results), esto solo devuelve la ULTIMA version de
    cada caso -- `id` (rowid real, INTEGER PRIMARY KEY) crece con el orden de insercion, asi
    que MAX(id) por caso identifica la mas reciente sin depender de analyzed_at (que puede ser
    NULL en un caso todavia sin veredicto). El calculo de "ultima version" va SIN los filtros
    de fecha/direccion de esta funcion -- filtrarlo ahi tambien podria, si un caso se reabre y
    cierra en otra fecha entre corridas, perder de vista su version mas reciente o mostrar una
    vieja por error."""
    clauses = ["id IN (SELECT MAX(id) FROM benchmark_result GROUP BY id_atencion, direction)"]
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
        for bool_column in (
            "has_farewell",
            "handled_well_for_complexity",
            "spelling_ok",
            "had_transfer",
            "informed_transfer",
            "quality_ok",
        ):
            row[bool_column] = None if row[bool_column] is None else bool(row[bool_column])
        raw_agents = row["transferred_from_agents"]
        row["transferred_from_agents"] = json.loads(raw_agents) if raw_agents else []
        rows.append(row)
    return rows


def create_benchmark_run(
    conn: DBConnection,
    started_at: str,
    date_from: str | None,
    date_to: str | None,
    force_reanalyze: bool,
    directions: list[str],
) -> int:
    """Registra el arranque de una corrida de benchmarks -- pipeline.run_benchmark_cycle() la
    llama ANTES de resolver el proveedor LLM (que puede fallar si nadie lo configuro todavia),
    para que ese fallo tambien quede trazado en el historial via finish_benchmark_run(). Usa
    execute() (no executescript()) a proposito -- confirmado en turso_serverless que solo
    execute() popula cursor.lastrowid para un INSERT, igual que sqlite3.Cursor.lastrowid."""
    cursor = conn.execute(
        "INSERT INTO benchmark_run (started_at, date_from, date_to, force_reanalyze, directions) "
        "VALUES (?, ?, ?, ?, ?)",
        (started_at, date_from, date_to, int(force_reanalyze), json.dumps(directions)),
    )
    conn.commit()
    return cursor.lastrowid


def finish_benchmark_run(
    conn: DBConnection,
    run_id: int,
    finished_at: str,
    ok: bool,
    summary_json: str,
    error: str | None = None,
) -> None:
    conn.execute(
        "UPDATE benchmark_run SET finished_at = ?, ok = ?, summary_json = ?, error = ? "
        "WHERE id = ?",
        (finished_at, int(ok), summary_json, error, run_id),
    )
    conn.commit()


def reconcile_orphaned_benchmark_runs(
    conn: DBConnection, now: str, error_message: str
) -> list[int]:
    """IDs de benchmark_run con `finished_at IS NULL` -- arrancaron pero nunca llegaron a
    finish_benchmark_run() porque el proceso murio a mitad de camino (ej. Render free tier
    reiniciando el dyno durante una corrida de horas). Sin esto quedan "corriendo" para
    siempre en el historial -- se marcan como fallidas con `error_message` en vez de eso. Se
    llama una sola vez al arrancar el proceso, ver benchmarks.state.reconcile_startup_state."""
    ids = [
        row[0]
        for row in conn.execute("SELECT id FROM benchmark_run WHERE finished_at IS NULL").fetchall()
    ]
    for run_id in ids:
        finish_benchmark_run(conn, run_id, now, False, "[]", error=error_message)
    return ids


def list_benchmark_runs(conn: DBConnection, limit: int = 50) -> list[dict]:
    cursor = conn.execute(
        "SELECT id, started_at, finished_at, ok, date_from, date_to, force_reanalyze, "
        "directions, summary_json, error FROM benchmark_run ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    runs = []
    for row in cursor.fetchall():
        runs.append(
            {
                "id": row[0],
                "started_at": row[1],
                "finished_at": row[2],
                "ok": None if row[3] is None else bool(row[3]),
                "date_from": row[4],
                "date_to": row[5],
                "force_reanalyze": bool(row[6]),
                "directions": json.loads(row[7]),
                "result_directions": json.loads(row[8]) if row[8] else [],
                "error": row[9],
            }
        )
    return runs
