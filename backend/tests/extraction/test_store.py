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
