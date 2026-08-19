import sqlite3

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
