import json
import sqlite3
from datetime import datetime, timedelta, timezone

from app.extraction import store


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    store._init_schema(conn)
    return conn


def test_save_sync_status_then_load_returns_the_same_dict():
    conn = _conn()

    store.save_sync_status(
        conn, "last_run", {"ok": True, "started_at": "2026-08-18T00:00:00"}, "2026-08-18T00:00:00"
    )

    assert store.load_sync_status(conn, "last_run") == {
        "ok": True,
        "started_at": "2026-08-18T00:00:00",
    }


def test_load_sync_status_returns_none_when_nothing_saved_for_that_kind():
    conn = _conn()

    assert store.load_sync_status(conn, "last_run") is None


def test_save_sync_status_overwrites_the_previous_value_for_the_same_kind():
    conn = _conn()
    store.save_sync_status(conn, "last_run", {"ok": True}, "2026-08-18T00:00:00")

    store.save_sync_status(conn, "last_run", {"ok": False}, "2026-08-18T01:00:00")

    assert store.load_sync_status(conn, "last_run") == {"ok": False}


def test_save_sync_status_keeps_separate_kinds_independent():
    conn = _conn()
    store.save_sync_status(conn, "last_run", {"ok": True}, "2026-08-18T00:00:00")
    store.save_sync_status(
        conn, "historical_backfill_status", {"phase": "done"}, "2026-08-18T00:00:00"
    )

    assert store.load_sync_status(conn, "last_run") == {"ok": True}
    assert store.load_sync_status(conn, "historical_backfill_status") == {"phase": "done"}


def _attention_row(id_atencion: str, fecha_registro) -> dict:
    return {
        "ID atención": id_atencion,
        "Estado": "Abierta",
        "Agente": "Ana",
        "Campaña": "Soporte",
        "Fecha registro": fecha_registro,
        "Fecha final": None,
        "Número cliente": "999999999",
    }


def test_history_rows_returns_everything_when_no_date_filter_given():
    conn = _conn()
    rows = [_attention_row("1", "16/08/2026"), _attention_row("2", "18/08/2026")]
    store.upsert_report_rows(conn, "attention", rows, "2026-08-19T00:00:00")

    history = store.history_rows(conn, "attention")

    assert {row["ID atención"] for row in history} == {"1", "2"}


def test_history_rows_filters_by_date_range_crossing_a_month_boundary():
    conn = _conn()
    rows = [
        _attention_row("before", "27/08/2026"),
        _attention_row("start", "28/08/2026"),
        _attention_row("middle", "31/08/2026"),
        _attention_row("end", "01/09/2026"),
        _attention_row("after", "05/09/2026"),
    ]
    store.upsert_report_rows(conn, "attention", rows, "2026-08-19T00:00:00")

    history = store.history_rows(conn, "attention", "2026-08-28", "2026-09-01")

    assert {row["ID atención"] for row in history} == {"start", "middle", "end"}


def test_history_rows_single_day_shortcut_when_date_to_omitted():
    conn = _conn()
    rows = [_attention_row("today", "18/08/2026"), _attention_row("other", "19/08/2026")]
    store.upsert_report_rows(conn, "attention", rows, "2026-08-19T00:00:00")

    history = store.history_rows(conn, "attention", "2026-08-18")

    assert [row["ID atención"] for row in history] == ["today"]


def test_history_rows_excludes_null_malformed_and_already_iso_dates_from_range_filter():
    conn = _conn()
    rows = [
        _attention_row("in_range", "18/08/2026"),
        _attention_row("null_date", None),
        _attention_row("malformed", "not-a-date"),
        # Un valor ya-ISO tiene los mismos 10 caracteres que DD/MM/YYYY -- sin la guarda GLOB,
        # un substr()/|| ingenuo lo convertiria en una clave de orden corrupta pero plausible.
        _attention_row("already_iso", "2026-08-18"),
    ]
    store.upsert_report_rows(conn, "attention", rows, "2026-08-19T00:00:00")

    history = store.history_rows(conn, "attention", "2026-08-01", "2026-08-31")

    assert [row["ID atención"] for row in history] == ["in_range"]


def test_history_rows_ignores_date_filter_for_reports_without_a_mapped_date_column():
    conn = _conn()
    rows = [
        {
            "Atención ID": "1",
            "Fecha": "2026-08-01",
            "Hora": "10:00:00",
            "Agente Origen": "Ana",
            "Destino": "Luis",
        }
    ]
    store.upsert_report_rows(conn, "transfer", rows, "2026-08-19T00:00:00")

    # "transfer" no esta en _HISTORY_DATE_COLUMN (su "fecha" ya viene en ISO, formato distinto
    # al DD/MM/YYYY de los demas reportes, y de todos modos nunca se filtra por dia -- ver
    # store.py). Pasarle date_from/date_to por error no debe devolver una lista vacia.
    history = store.history_rows(conn, "transfer", "2026-08-16", "2026-08-18")

    assert len(history) == 1


def test_daily_counts_groups_rows_by_calendar_day():
    conn = _conn()
    rows = [
        _attention_row("a", "18/08/2026"),
        _attention_row("b", "18/08/2026"),
        _attention_row("c", "19/08/2026"),
    ]
    store.upsert_report_rows(conn, "attention", rows, "2026-08-19T00:00:00")

    counts = store.daily_counts(conn, "attention")

    assert counts == [
        {"date": "2026-08-18", "count": 2},
        {"date": "2026-08-19", "count": 1},
    ]


def test_daily_counts_filters_by_date_range():
    conn = _conn()
    rows = [
        _attention_row("before", "27/08/2026"),
        _attention_row("in_range", "28/08/2026"),
        _attention_row("after", "01/09/2026"),
    ]
    store.upsert_report_rows(conn, "attention", rows, "2026-08-19T00:00:00")

    counts = store.daily_counts(conn, "attention", "2026-08-28", "2026-08-31")

    assert counts == [{"date": "2026-08-28", "count": 1}]


def test_daily_counts_single_day_shortcut_when_date_to_omitted():
    conn = _conn()
    rows = [_attention_row("today", "18/08/2026"), _attention_row("other", "19/08/2026")]
    store.upsert_report_rows(conn, "attention", rows, "2026-08-19T00:00:00")

    counts = store.daily_counts(conn, "attention", "2026-08-18")

    assert counts == [{"date": "2026-08-18", "count": 1}]


def test_daily_counts_excludes_null_and_malformed_dates():
    conn = _conn()
    rows = [
        _attention_row("valid", "18/08/2026"),
        _attention_row("null_date", None),
        _attention_row("malformed", "not-a-date"),
    ]
    store.upsert_report_rows(conn, "attention", rows, "2026-08-19T00:00:00")

    counts = store.daily_counts(conn, "attention")

    assert counts == [{"date": "2026-08-18", "count": 1}]


def test_daily_counts_filters_by_agentes_with_sin_agente_fallback():
    conn = _conn()
    _seed(
        conn,
        "attention",
        [
            _row("ana", agente="Ana", fecha_registro="18/08/2026"),
            _row("bot", agente="Bot", fecha_registro="18/08/2026"),
            _row("dash", agente="-", fecha_registro="18/08/2026"),
        ],
    )

    counts = store.daily_counts(conn, "attention", agentes=["Ana", "Sin agente"])

    assert counts == [{"date": "2026-08-18", "count": 2}]


def test_daily_counts_agentes_empty_list_matches_nothing():
    conn = _conn()
    _seed(conn, "attention", [_row("ana", agente="Ana")])

    counts = store.daily_counts(conn, "attention", agentes=[])

    assert counts == []


def test_migration_adds_time_columns_and_backfills_them_from_row_json():
    conn = sqlite3.connect(":memory:")
    # Simula el esquema pre-migracion (sin hora_registro/hora_final) que ya existe en el Turso
    # en vivo -- _init_schema debe agregar las columnas y rellenarlas desde row_json.
    conn.executescript(
        """
        CREATE TABLE attention (
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
        """
    )
    row = {"ID atención": "1", "Hora registro": "10:00:00", "Hora final": "11:30:00"}
    conn.execute(
        "INSERT INTO attention (id_atencion, first_seen_at, last_seen_at, row_json) "
        "VALUES (?, ?, ?, ?)",
        ("1", "2026-08-19T00:00:00", "2026-08-19T00:00:00", json.dumps(row)),
    )
    conn.commit()

    store._init_schema(conn)

    assert {"hora_registro", "hora_final"} <= store._existing_columns(conn, "attention")
    cursor = conn.execute(
        "SELECT hora_registro, hora_final FROM attention WHERE id_atencion = '1'"
    )
    assert cursor.fetchone() == ("10:00:00", "11:30:00")


def _lima_naive(dt_utc: datetime) -> tuple[str, str]:
    """Componentes 'DD/MM/YYYY'/'HH:MM:SS' (formato de fecha_registro/fecha_final) en hora Lima
    (UTC-5) para un instante UTC real -- usado para construir filas cuyo elapsed calculado en SQL
    (que compara contra julianday('now'), UTC real) tenga un valor predecible relativo al momento
    en que corre el test."""
    lima = dt_utc - timedelta(hours=5)
    return lima.strftime("%d/%m/%Y"), lima.strftime("%H:%M:%S")


def _lima_naive_iso(dt_utc: datetime) -> tuple[str, str]:
    """Igual que _lima_naive pero en 'YYYY-MM-DD' -- formato de transfer.fecha."""
    lima = dt_utc - timedelta(hours=5)
    return lima.strftime("%Y-%m-%d"), lima.strftime("%H:%M:%S")


def _row(
    id_atencion: str,
    *,
    estado: str = "Abierta",
    agente: str = "Ana",
    campana: str = "Soporte",
    fecha_registro: str = "18/08/2026",
    hora_registro: str = "08:00:00",
    fecha_final: str | None = None,
    hora_final: str | None = None,
    numero_cliente: str = "999999999",
) -> dict:
    return {
        "ID atención": id_atencion,
        "Estado": estado,
        "Agente": agente,
        "Campaña": campana,
        "Fecha registro": fecha_registro,
        "Hora registro": hora_registro,
        "Fecha final": fecha_final,
        "Hora final": hora_final,
        "Número cliente": numero_cliente,
    }


def _seed(conn, report_name: str, rows: list[dict]) -> None:
    store.upsert_report_rows(conn, report_name, rows, "2026-08-19T00:00:00")


def test_attention_records_page_direction_all_unions_both_tables_tagged():
    conn = _conn()
    _seed(conn, "attention", [_row("in1")])
    _seed(conn, "outboundattention", [_row("out1")])

    page = store.attention_records_page(conn, direction="all", page=1, page_size=50)

    by_id = {row["ID atención"]: row["direction"] for row in page.rows}
    assert by_id == {"in1": "incoming", "out1": "outgoing"}


def test_attention_records_page_direction_incoming_excludes_outbound_table():
    conn = _conn()
    _seed(conn, "attention", [_row("in1")])
    _seed(conn, "outboundattention", [_row("out1")])

    page = store.attention_records_page(conn, direction="incoming", page=1, page_size=50)

    assert [row["ID atención"] for row in page.rows] == ["in1"]


def test_attention_records_page_filters_by_estados_and_sin_estado_fallback():
    conn = _conn()
    _seed(
        conn,
        "attention",
        [
            _row("abierta", estado="Abierta"),
            _row("cerrada", estado="Cerrada"),
            _row("blank", estado=""),
        ],
    )

    page = store.attention_records_page(
        conn, direction="all", estados=["Abierta", "Sin estado"], page=1, page_size=50
    )

    assert {row["ID atención"] for row in page.rows} == {"abierta", "blank"}


def test_attention_records_page_estados_empty_list_matches_nothing():
    conn = _conn()
    _seed(conn, "attention", [_row("1")])

    page = store.attention_records_page(conn, direction="all", estados=[], page=1, page_size=50)

    assert page.rows == []
    assert page.total == 0


def test_attention_records_page_filters_by_campana_with_sin_campana_fallback():
    conn = _conn()
    _seed(
        conn,
        "attention",
        [_row("soporte", campana="Soporte"), _row("blank", campana="")],
    )

    page = store.attention_records_page(
        conn, direction="all", campana="Sin campaña", page=1, page_size=50
    )

    assert [row["ID atención"] for row in page.rows] == ["blank"]


def test_attention_records_page_filters_by_agente_with_sin_agente_fallback_for_dash():
    conn = _conn()
    _seed(
        conn,
        "attention",
        [_row("ana", agente="Ana"), _row("dash", agente="-"), _row("blank", agente="")],
    )

    page = store.attention_records_page(
        conn, direction="all", agentes=["Sin agente"], page=1, page_size=50
    )

    assert {row["ID atención"] for row in page.rows} == {"dash", "blank"}


def test_attention_records_page_filters_by_multiple_agentes():
    conn = _conn()
    _seed(
        conn,
        "attention",
        [
            _row("ana", agente="Ana"),
            _row("luis", agente="Luis"),
            _row("sofia", agente="Sofia"),
        ],
    )

    page = store.attention_records_page(
        conn, direction="all", agentes=["Ana", "Luis"], page=1, page_size=50
    )

    assert {row["ID atención"] for row in page.rows} == {"ana", "luis"}


def test_attention_records_page_agentes_empty_list_matches_nothing():
    conn = _conn()
    _seed(conn, "attention", [_row("1")])

    page = store.attention_records_page(conn, direction="all", agentes=[], page=1, page_size=50)

    assert page.rows == []
    assert page.total == 0


def test_attention_records_page_filters_by_date_range():
    conn = _conn()
    _seed(
        conn,
        "attention",
        [
            _row("in_range", fecha_registro="18/08/2026"),
            _row("out_of_range", fecha_registro="01/09/2026"),
        ],
    )

    page = store.attention_records_page(
        conn, direction="all", date_from="2026-08-18", date_to="2026-08-18", page=1, page_size=50
    )

    assert [row["ID atención"] for row in page.rows] == ["in_range"]


def test_attention_records_page_orders_by_elapsed_time_with_agent_longest_first():
    conn = _conn()
    now = datetime.now(timezone.utc)
    old_fecha, old_hora = _lima_naive(now - timedelta(hours=5))
    recent_fecha, recent_hora = _lima_naive(now - timedelta(minutes=10))
    _seed(
        conn,
        "attention",
        [
            _row("recent", fecha_registro=recent_fecha, hora_registro=recent_hora),
            _row("old", fecha_registro=old_fecha, hora_registro=old_hora),
            _row("no_agent", agente="-"),
        ],
    )

    page = store.attention_records_page(conn, direction="all", page=1, page_size=50)

    assert [row["ID atención"] for row in page.rows] == ["old", "recent", "no_agent"]


def test_attention_records_page_prefers_latest_transfer_hop_over_registration_time():
    conn = _conn()
    now = datetime.now(timezone.utc)
    long_ago_fecha, long_ago_hora = _lima_naive(now - timedelta(hours=3))
    recent_fecha, recent_hora = _lima_naive(now - timedelta(minutes=20))
    _seed(
        conn,
        "attention",
        [
            # Registrada hace 3h, pero transferida a su agente actual hace solo 5 min -- su
            # elapsed real (~5min) debe medirse desde la transferencia, no desde el registro
            # (que daria, incorrectamente, ~3h).
            _row("transferred", fecha_registro=long_ago_fecha, hora_registro=long_ago_hora),
            # Registrada hace 20 min, nunca transferida -- elapsed real ~20min.
            _row("never_transferred", fecha_registro=recent_fecha, hora_registro=recent_hora),
        ],
    )
    transfer_fecha, transfer_hora = _lima_naive_iso(now - timedelta(minutes=5))
    _seed(
        conn,
        "transfer",
        [
            {
                "Atención ID": "transferred",
                "Fecha": transfer_fecha,
                "Hora": transfer_hora,
                "Agente Origen": "Ana",
                "Destino": "Luis",
            }
        ],
    )

    page = store.attention_records_page(conn, direction="all", page=1, page_size=50)

    # "never_transferred" (~20min con su agente) debe ordenar antes que "transferred" (~5min con
    # su agente actual, pese a estar registrada desde hace 3h) -- confirma que el sort usa el
    # ultimo hop de transfer, no fecha_registro, para "transferred".
    assert [row["ID atención"] for row in page.rows] == ["never_transferred", "transferred"]


def test_attention_records_page_freezes_elapsed_time_for_closed_records():
    conn = _conn()
    _seed(
        conn,
        "attention",
        [
            _row(
                "closed_long_ago",
                fecha_registro="01/01/2026",
                hora_registro="08:00:00",
                fecha_final="01/01/2026",
                hora_final="10:00:00",
            )
        ],
    )

    page = store.attention_records_page(conn, direction="all", page=1, page_size=50)

    assert len(page.rows) == 1
    # No es stale (esta cerrada) aunque su duracion historica (2h) supere el umbral de stale.
    assert page.stale_count == 0


def test_attention_records_page_stale_count_only_counts_open_records_past_threshold():
    conn = _conn()
    now = datetime.now(timezone.utc)
    stale_fecha, stale_hora = _lima_naive(now - timedelta(hours=2))
    fresh_fecha, fresh_hora = _lima_naive(now - timedelta(minutes=5))
    closed_fecha, closed_hora = _lima_naive(now - timedelta(hours=1))
    _seed(
        conn,
        "attention",
        [
            _row("stale_open", fecha_registro=stale_fecha, hora_registro=stale_hora),
            _row("fresh_open", fecha_registro=fresh_fecha, hora_registro=fresh_hora),
            # Misma "since" que stale_open (hace 2h), pero cerrada hace 1h -- no cuenta como
            # stale porque ya esta cerrada, sin importar cuanto duro mientras estuvo abierta.
            _row(
                "stale_but_closed",
                fecha_registro=stale_fecha,
                hora_registro=stale_hora,
                fecha_final=closed_fecha,
                hora_final=closed_hora,
            ),
        ],
    )

    page = store.attention_records_page(conn, direction="all", page=1, page_size=50)

    assert page.stale_count == 1


def test_attention_records_page_paginates_with_page_and_page_size():
    conn = _conn()
    _seed(
        conn,
        "attention",
        [
            _row(str(i), fecha_registro="18/08/2026", hora_registro=f"{8 + i:02d}:00:00")
            for i in range(5)
        ],
    )

    page1 = store.attention_records_page(conn, direction="all", page=1, page_size=2)
    page2 = store.attention_records_page(conn, direction="all", page=2, page_size=2)

    assert page1.total == 5
    assert len(page1.rows) == 2
    assert len(page2.rows) == 2
    assert {row["ID atención"] for row in page1.rows}.isdisjoint(
        {row["ID atención"] for row in page2.rows}
    )


def test_attention_records_page_returns_transfers_only_for_ids_on_the_page():
    conn = _conn()
    _seed(conn, "attention", [_row("on_page")])
    _seed(
        conn,
        "transfer",
        [
            {
                "Atención ID": "on_page",
                "Fecha": "2026-08-18",
                "Hora": "09:00:00",
                "Agente Origen": "Ana",
                "Destino": "Luis",
            },
            {
                "Atención ID": "not_on_page",
                "Fecha": "2026-08-18",
                "Hora": "09:00:00",
                "Agente Origen": "Ana",
                "Destino": "Luis",
            },
        ],
    )

    page = store.attention_records_page(conn, direction="all", page=1, page_size=50)

    assert [t["Atención ID"] for t in page.transfers] == ["on_page"]


def _closed_attention_row(id_atencion: str, fecha_final: str, estado: str = "Cerrada") -> dict:
    return {
        "ID atención": id_atencion,
        "Estado": estado,
        "Agente": "Ana",
        "Campaña": "Soporte",
        "Fecha registro": "01/08/2026",
        "Hora registro": "08:00:00",
        "Fecha final": fecha_final,
        "Hora final": "09:00:00",
        "Número cliente": "999999999",
        "Tiempo de primera respuesta": "00:01:30",
    }


def test_closed_case_rows_filters_by_estado():
    conn = _conn()
    store.upsert_report_rows(
        conn,
        "attention",
        [
            _closed_attention_row("1", "18/08/2026", estado="Cerrada"),
            _closed_attention_row("2", "18/08/2026", estado="Abierta"),
        ],
        "2026-08-18T00:00:00",
    )

    rows = store.closed_case_rows(conn, "attention", estados=["Cerrada"])

    assert set(rows) == {"1"}
    assert rows["1"]["Agente"] == "Ana"


def test_closed_case_rows_respects_date_from_against_fecha_final():
    conn = _conn()
    store.upsert_report_rows(
        conn,
        "attention",
        [
            _closed_attention_row("old", "01/08/2026"),
            _closed_attention_row("recent", "18/08/2026"),
        ],
        "2026-08-18T00:00:00",
    )

    rows = store.closed_case_rows(
        conn, "attention", estados=["Cerrada"], date_from="2026-08-15"
    )

    assert set(rows) == {"recent"}


def test_closed_case_rows_respects_date_to_as_well():
    conn = _conn()
    store.upsert_report_rows(
        conn,
        "attention",
        [
            _closed_attention_row("before", "10/08/2026"),
            _closed_attention_row("in_range", "18/08/2026"),
            _closed_attention_row("after", "25/08/2026"),
        ],
        "2026-08-18T00:00:00",
    )

    rows = store.closed_case_rows(
        conn, "attention", estados=["Cerrada"], date_from="2026-08-15", date_to="2026-08-20"
    )

    assert set(rows) == {"in_range"}


def test_closed_case_rows_date_from_without_date_to_stays_open_ended():
    # Sin date_to, el rango sigue abierto hacia adelante (comportamiento historico) -- no usar
    # el idiom "date_to or date_from" en el caller si se quiere este default.
    conn = _conn()
    store.upsert_report_rows(
        conn,
        "attention",
        [
            _closed_attention_row("old", "01/08/2026"),
            _closed_attention_row("recent", "18/08/2026"),
            _closed_attention_row("future", "25/08/2026"),
        ],
        "2026-08-18T00:00:00",
    )

    rows = store.closed_case_rows(conn, "attention", estados=["Cerrada"], date_from="2026-08-15")

    assert set(rows) == {"recent", "future"}


def test_closed_case_rows_returns_empty_dict_when_estados_is_empty():
    conn = _conn()
    store.upsert_report_rows(
        conn, "attention", [_closed_attention_row("1", "18/08/2026")], "2026-08-18T00:00:00"
    )

    assert store.closed_case_rows(conn, "attention", estados=[]) == {}


def test_already_benchmarked_ids_only_counts_real_quality_verdicts():
    conn = _conn()
    store.record_benchmark_results(
        conn,
        [
            {
                "id_atencion": "judged",
                "direction": "attention",
                "has_greeting": True,
                "has_farewell": True,
                "row_json": {},
            },
            {
                "id_atencion": "no_pdf_yet",
                "direction": "attention",
                "has_greeting": None,
                "has_farewell": None,
                "row_json": {},
            },
        ],
        "2026-08-18T00:00:00",
    )

    already = store.already_benchmarked_ids(
        conn, "attention", ["judged", "no_pdf_yet", "never_seen"]
    )

    assert already == {"judged"}


def test_already_benchmarked_ids_returns_empty_set_for_no_ids():
    conn = _conn()

    assert store.already_benchmarked_ids(conn, "attention", []) == set()


def test_record_benchmark_results_inserts_row_without_quality_when_no_pdf():
    conn = _conn()

    store.record_benchmark_results(
        conn,
        [
            {
                "id_atencion": "1",
                "direction": "attention",
                "agente": "Ana",
                "campana": "Soporte",
                "estado": "Cerrada",
                "first_response_seconds": 90.0,
                "has_greeting": None,
                "has_farewell": None,
                "row_json": {"ID atención": "1"},
            }
        ],
        "2026-08-18T00:00:00",
    )

    rows = store.benchmark_result_rows(conn)
    assert len(rows) == 1
    assert rows[0]["has_greeting"] is None
    assert rows[0]["analyzed_at"] is None
    assert rows[0]["first_response_seconds"] == 90.0


def test_record_benchmark_results_extracts_fecha_hora_final_and_cliente_from_row_json():
    conn = _conn()

    store.record_benchmark_results(
        conn,
        [
            {
                "id_atencion": "1",
                "direction": "attention",
                "agente": "Ana",
                "row_json": {
                    "ID atención": "1",
                    "Fecha final": "18/08/2026",
                    "Hora final": "14:32:10",
                    "Nombre de cliente": "Ana Perez",
                },
            }
        ],
        "2026-08-18T00:00:00",
    )

    rows = store.benchmark_result_rows(conn)
    assert rows[0]["fecha_final"] == "18/08/2026"
    assert rows[0]["hora_final"] == "14:32:10"
    assert rows[0]["cliente"] == "Ana Perez"


def test_record_benchmark_results_appends_instead_of_overwriting_on_a_later_run():
    conn = _conn()
    store.record_benchmark_results(
        conn,
        [
            {
                "id_atencion": "1",
                "direction": "attention",
                "has_greeting": None,
                "has_farewell": None,
                "row_json": {},
            }
        ],
        "2026-08-18T00:00:00",
        run_id=1,
    )

    store.record_benchmark_results(
        conn,
        [
            {
                "id_atencion": "1",
                "direction": "attention",
                "has_greeting": True,
                "has_farewell": True,
                "llm_model": "gpt-4o-mini",
                "row_json": {},
            }
        ],
        "2026-08-19T00:00:00",
        run_id=2,
    )

    # Dos filas, no una -- la corrida anterior no se pisa, queda de historial.
    all_rows = conn.execute(
        "SELECT run_id, has_greeting FROM benchmark_result WHERE id_atencion = '1' ORDER BY id"
    ).fetchall()
    assert all_rows == [(1, None), (2, 1)]

    # benchmark_result_rows() sigue mostrando solo la version mas reciente.
    rows = store.benchmark_result_rows(conn)
    assert len(rows) == 1
    assert rows[0]["has_greeting"] is True
    assert rows[0]["quality_ok"] is True
    assert rows[0]["analyzed_at"] == "2026-08-19T00:00:00"


def test_record_benchmark_results_quality_ok_is_false_when_only_one_flag_true():
    conn = _conn()
    store.record_benchmark_results(
        conn,
        [
            {
                "id_atencion": "1",
                "direction": "attention",
                "has_greeting": True,
                "has_farewell": False,
                "row_json": {},
            }
        ],
        "2026-08-18T00:00:00",
    )

    rows = store.benchmark_result_rows(conn)
    assert rows[0]["quality_ok"] is False


def test_record_benchmark_results_skips_rows_without_id_atencion():
    conn = _conn()

    result = store.record_benchmark_results(
        conn,
        [{"id_atencion": None, "direction": "attention", "row_json": {}}],
        "2026-08-18T00:00:00",
    )

    assert result.rows_upserted == 0
    assert result.rows_skipped == 1


def test_benchmark_result_rows_filters_by_direction_and_date_range():
    conn = _conn()
    store.record_benchmark_results(
        conn,
        [
            {
                "id_atencion": "in_dir",
                "direction": "attention",
                "row_json": {"Fecha final": "18/08/2026"},
            },
            {
                "id_atencion": "other_dir",
                "direction": "outboundattention",
                "row_json": {"Fecha final": "18/08/2026"},
            },
        ],
        "2026-08-18T00:00:00",
    )
    store.record_benchmark_results(
        conn,
        [{"id_atencion": "old", "direction": "attention", "row_json": {"Fecha final": "01/08/2026"}}],
        "2026-08-01T00:00:00",
    )

    rows = store.benchmark_result_rows(
        conn, direction="attention", date_from="2026-08-15", date_to="2026-08-20"
    )

    assert [r["id_atencion"] for r in rows] == ["in_dir"]


def test_benchmark_result_rows_filters_by_the_cases_own_close_date_not_when_it_was_analyzed():
    # El bug real que motivo este fix: un caso cerrado AYER pero analizado (procesado por
    # el pipeline) HOY no debe aparecer al filtrar "hoy" -- first_recorded_at/observed_at
    # son fechas de proceso, no la fecha de negocio real del caso.
    conn = _conn()
    store.record_benchmark_results(
        conn,
        [
            {
                "id_atencion": "closed_yesterday",
                "direction": "attention",
                "row_json": {"Fecha final": "25/08/2026"},
            },
            {
                "id_atencion": "closed_today",
                "direction": "attention",
                "row_json": {"Fecha final": "26/08/2026"},
            },
        ],
        # Ambos casos se procesaron (analizaron) el mismo dia -- 2026-08-26 --
        # independientemente de que uno cerro ayer.
        "2026-08-26T23:00:00",
    )

    rows = store.benchmark_result_rows(conn, date_from="2026-08-26")

    assert [r["id_atencion"] for r in rows] == ["closed_today"]


def test_benchmark_result_rows_returns_only_the_latest_version_per_case():
    conn = _conn()
    store.record_benchmark_results(
        conn,
        [
            {
                "id_atencion": "1",
                "direction": "attention",
                "has_greeting": False,
                "has_farewell": False,
                "row_json": {"Fecha final": "18/08/2026"},
            }
        ],
        "2026-08-18T00:00:00",
        run_id=1,
    )
    store.record_benchmark_results(
        conn,
        [
            {
                "id_atencion": "1",
                "direction": "attention",
                "has_greeting": True,
                "has_farewell": True,
                "row_json": {"Fecha final": "18/08/2026"},
            }
        ],
        "2026-08-19T00:00:00",
        run_id=2,
    )

    rows = store.benchmark_result_rows(conn)

    assert len(rows) == 1
    assert rows[0]["has_greeting"] is True
    assert rows[0]["analyzed_at"] == "2026-08-19T00:00:00"


def test_migrate_benchmark_result_columns_backfills_new_columns_from_row_json():
    # Simula una Turso en vivo donde benchmark_result ya existia ANTES de que fecha_final
    # se agregara a la tabla -- CREATE TABLE IF NOT EXISTS no le agrega la columna a una
    # tabla que ya existe, asi que _init_schema depende de esta migracion aparte.
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE benchmark_result (
            id_atencion TEXT NOT NULL,
            direction TEXT NOT NULL,
            agente TEXT,
            campana TEXT,
            estado TEXT,
            first_response_seconds REAL,
            has_greeting INTEGER,
            has_farewell INTEGER,
            quality_ok INTEGER,
            llm_model TEXT,
            llm_raw TEXT,
            llm_notes TEXT,
            analyzed_at TEXT,
            first_recorded_at TEXT NOT NULL,
            last_updated_at TEXT NOT NULL,
            row_json TEXT NOT NULL,
            PRIMARY KEY (id_atencion, direction)
        )
        """
    )
    conn.execute(
        "INSERT INTO benchmark_result "
        "(id_atencion, direction, first_recorded_at, last_updated_at, row_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "1",
            "attention",
            "2026-08-01T00:00:00",
            "2026-08-01T00:00:00",
            json.dumps(
                {
                    "Fecha final": "18/08/2026",
                    "Hora final": "14:32:10",
                    "Nombre de cliente": "Ana Perez",
                }
            ),
        ),
    )
    conn.commit()

    store._init_schema(conn)

    row = conn.execute(
        "SELECT fecha_final, hora_final, cliente FROM benchmark_result WHERE id_atencion = '1'"
    ).fetchone()
    assert row == ("18/08/2026", "14:32:10", "Ana Perez")

    # La migracion de versionado (_migrate_benchmark_result_versioning) corre despues de esta
    # y reconstruye la tabla -- confirma que preservo la fila (con run_id NULL, de antes de
    # que existiera benchmark_run) y que la tabla vieja quedo renombrada, no borrada.
    run_id = conn.execute(
        "SELECT run_id FROM benchmark_result WHERE id_atencion = '1'"
    ).fetchone()[0]
    assert run_id is None
    backup_count = conn.execute(
        "SELECT COUNT(*) FROM benchmark_result_pre_versioning"
    ).fetchone()[0]
    assert backup_count == 1


def test_migrate_benchmark_result_versioning_allows_duplicate_case_rows_now():
    # La prueba mas directa de que la PK vieja (id_atencion, direction) ya no existe: dos
    # filas para el mismo caso deben poder convivir despues de la migracion.
    conn = _conn()

    store.record_benchmark_results(
        conn,
        [{"id_atencion": "1", "direction": "attention", "row_json": {}}],
        "2026-08-18T00:00:00",
        run_id=1,
    )
    store.record_benchmark_results(
        conn,
        [{"id_atencion": "1", "direction": "attention", "row_json": {}}],
        "2026-08-19T00:00:00",
        run_id=2,
    )

    count = conn.execute(
        "SELECT COUNT(*) FROM benchmark_result WHERE id_atencion = '1'"
    ).fetchone()[0]
    assert count == 2


def test_migrate_benchmark_result_versioning_is_a_noop_once_run_id_exists():
    conn = _conn()  # _conn() ya corre _init_schema() una vez -- run_id ya existe
    store.record_benchmark_results(
        conn,
        [{"id_atencion": "1", "direction": "attention", "row_json": {}}],
        "2026-08-18T00:00:00",
        run_id=1,
    )

    store._init_schema(conn)  # correrlo de nuevo no debe tocar los datos ni reventar

    count = conn.execute("SELECT COUNT(*) FROM benchmark_result").fetchone()[0]
    assert count == 1
    # No debe existir una segunda tabla de respaldo por correr la migracion dos veces.
    backup_tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'benchmark_result_pre_versioning%'"
    ).fetchall()
    assert len(backup_tables) == 0


def test_create_benchmark_run_then_list_returns_it():
    conn = _conn()

    run_id = store.create_benchmark_run(
        conn, "2026-08-27T00:00:00", "2026-08-27", "2026-08-27", False, ["attention"]
    )

    runs = store.list_benchmark_runs(conn)
    assert len(runs) == 1
    assert runs[0]["id"] == run_id
    assert runs[0]["started_at"] == "2026-08-27T00:00:00"
    assert runs[0]["finished_at"] is None
    assert runs[0]["ok"] is None
    assert runs[0]["date_from"] == "2026-08-27"
    assert runs[0]["date_to"] == "2026-08-27"
    assert runs[0]["force_reanalyze"] is False
    assert runs[0]["directions"] == ["attention"]
    assert runs[0]["result_directions"] == []
    assert runs[0]["error"] is None


def test_finish_benchmark_run_updates_the_row():
    conn = _conn()
    run_id = store.create_benchmark_run(
        conn, "2026-08-27T00:00:00", None, None, True, ["attention", "outboundattention"]
    )

    store.finish_benchmark_run(
        conn,
        run_id,
        "2026-08-27T00:05:00",
        True,
        '[{"direction": "attention", "action": "analyzed"}]',
    )

    runs = store.list_benchmark_runs(conn)
    assert runs[0]["finished_at"] == "2026-08-27T00:05:00"
    assert runs[0]["ok"] is True
    assert runs[0]["result_directions"] == [{"direction": "attention", "action": "analyzed"}]


def test_finish_benchmark_run_records_the_error_on_failure():
    conn = _conn()
    run_id = store.create_benchmark_run(conn, "2026-08-27T00:00:00", None, None, False, ["attention"])

    store.finish_benchmark_run(
        conn, run_id, "2026-08-27T00:01:00", False, "[]", error="LLM no configurado"
    )

    runs = store.list_benchmark_runs(conn)
    assert runs[0]["ok"] is False
    assert runs[0]["error"] == "LLM no configurado"


def test_list_benchmark_runs_orders_most_recent_first_and_respects_limit():
    conn = _conn()
    for i in range(3):
        store.create_benchmark_run(
            conn, f"2026-08-2{i}T00:00:00", None, None, False, ["attention"]
        )

    runs = store.list_benchmark_runs(conn, limit=2)

    assert len(runs) == 2
    assert runs[0]["started_at"] == "2026-08-22T00:00:00"
    assert runs[1]["started_at"] == "2026-08-21T00:00:00"
