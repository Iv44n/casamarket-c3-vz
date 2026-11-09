import sqlite3

import pytest

from app.incidents import store

NOW = "2026-11-09T15:00:00+00:00"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    store._init_schema(conn)
    return conn


def _seed_catalog(conn: sqlite3.Connection) -> None:
    store.import_catalog_values(
        conn,
        {
            "origen": ["ADMIN WEB", "POS WEB"],
            "tipo": ["CONSULTAS", "BUG BLOQUEANTE"],
            "ambito": ["VENTAS", "CAJA"],
            "resultado": ["RESUELTO"],
        },
        NOW,
    )


def _input(**overrides) -> store.IncidentInput:
    values = {
        "fecha": "2026-11-09",
        "hora": "10:30",
        "cliente": "Bodega Uno",
        "telefono": "999000111",
        "agente": "Ana",
        "origen": "ADMIN WEB",
        "tipo": "CONSULTAS",
        "ambito": "VENTAS",
        "resultado": "",
        "descripcion": "No puede emitir boletas",
    }
    values.update(overrides)
    return store.IncidentInput(**values)


def _option_id(conn: sqlite3.Connection, category: str, value: str) -> int:
    return next(o.id for o in store.list_catalog(conn) if o.category == category and o.value == value)


def test_create_then_get_returns_the_incident_with_audit_fields():
    conn = _conn()
    _seed_catalog(conn)

    created = store.create_incident(conn, _input(), "rosa", NOW)

    assert store.get_incident(conn, created.id) == created
    assert created.created_by == "rosa"
    assert created.created_at == NOW
    assert created.updated_by is None


@pytest.mark.parametrize("category", ["origen", "tipo", "ambito", "resultado"])
def test_create_rejects_a_value_outside_the_catalog(category: str):
    conn = _conn()
    _seed_catalog(conn)

    with pytest.raises(store.InvalidCatalogValueError) as excinfo:
        store.create_incident(conn, _input(**{category: "INVENTADO"}), "rosa", NOW)

    assert excinfo.value.category == category


@pytest.mark.parametrize("category", ["origen", "tipo", "ambito"])
def test_create_requires_origen_tipo_and_ambito(category: str):
    conn = _conn()
    _seed_catalog(conn)

    with pytest.raises(store.InvalidCatalogValueError):
        store.create_incident(conn, _input(**{category: ""}), "rosa", NOW)


def test_create_rejects_a_deactivated_catalog_value():
    conn = _conn()
    _seed_catalog(conn)
    store.set_catalog_option_active(conn, _option_id(conn, "ambito", "CAJA"), False)

    with pytest.raises(store.InvalidCatalogValueError):
        store.create_incident(conn, _input(ambito="CAJA"), "rosa", NOW)


def test_update_keeps_accepting_a_value_deactivated_after_the_incident_was_created():
    conn = _conn()
    _seed_catalog(conn)
    created = store.create_incident(conn, _input(ambito="CAJA"), "rosa", NOW)
    store.set_catalog_option_active(conn, _option_id(conn, "ambito", "CAJA"), False)

    updated = store.update_incident(
        conn, created.id, _input(ambito="CAJA", descripcion="Corregida"), "luis", "2026-11-10T00:00:00"
    )

    assert updated is not None
    assert updated.descripcion == "Corregida"
    assert updated.updated_by == "luis"
    assert updated.created_by == "rosa"


def test_update_rejects_switching_to_a_deactivated_value():
    conn = _conn()
    _seed_catalog(conn)
    created = store.create_incident(conn, _input(), "rosa", NOW)
    store.set_catalog_option_active(conn, _option_id(conn, "ambito", "CAJA"), False)

    with pytest.raises(store.InvalidCatalogValueError):
        store.update_incident(conn, created.id, _input(ambito="CAJA"), "rosa", NOW)


def test_update_returns_none_for_an_unknown_incident():
    conn = _conn()
    _seed_catalog(conn)

    assert store.update_incident(conn, 999, _input(), "rosa", NOW) is None


def test_delete_is_logical_and_hides_the_incident():
    conn = _conn()
    _seed_catalog(conn)
    created = store.create_incident(conn, _input(), "rosa", NOW)

    assert store.delete_incident(conn, created.id, "luis", NOW) is True

    assert store.get_incident(conn, created.id) is None
    assert store.list_incidents(conn, "2026-11-09", "2026-11-09") == ([], False)
    assert store.delete_incident(conn, created.id, "luis", NOW) is False
    deleted_by = conn.execute(
        "SELECT deleted_by FROM manual_incident WHERE id = ?", (created.id,)
    ).fetchone()[0]
    assert deleted_by == "luis"


def test_list_filters_by_inclusive_date_range_newest_first():
    conn = _conn()
    _seed_catalog(conn)
    store.create_incident(conn, _input(fecha="2026-11-07", descripcion="antes"), "rosa", NOW)
    store.create_incident(conn, _input(fecha="2026-11-08", hora="09:00", descripcion="a"), "rosa", NOW)
    store.create_incident(conn, _input(fecha="2026-11-09", hora="08:00", descripcion="b"), "rosa", NOW)
    store.create_incident(conn, _input(fecha="2026-11-09", hora="11:00", descripcion="c"), "rosa", NOW)
    store.create_incident(conn, _input(fecha="2026-11-10", descripcion="despues"), "rosa", NOW)

    rows, truncated = store.list_incidents(conn, "2026-11-08", "2026-11-09")

    assert [r.descripcion for r in rows] == ["c", "b", "a"]
    assert truncated is False


def test_list_reports_truncation_past_the_limit():
    conn = _conn()
    _seed_catalog(conn)
    for i in range(3):
        store.create_incident(conn, _input(descripcion=f"n{i}"), "rosa", NOW)

    rows, truncated = store.list_incidents(conn, "2026-11-09", "2026-11-09", limit=2)

    assert len(rows) == 2
    assert truncated is True


def test_import_is_idempotent_and_never_reactivates_a_disabled_option():
    conn = _conn()
    values = {"origen": ["ADMIN WEB", "POS WEB"], "tipo": ["CONSULTAS"]}

    assert store.import_catalog_values(conn, values, NOW) == 3
    store.set_catalog_option_active(conn, _option_id(conn, "origen", "POS WEB"), False)

    assert store.import_catalog_values(conn, {**values, "ambito": ["CAJA"]}, NOW) == 1

    by_key = {(o.category, o.value): o for o in store.list_catalog(conn)}
    assert by_key[("origen", "POS WEB")].active is False
    assert by_key[("ambito", "CAJA")].source == "c3"


def test_add_catalog_option_rejects_a_duplicate():
    conn = _conn()
    store.add_catalog_option(conn, "origen", "PRESENCIAL", NOW)

    with pytest.raises(store.CatalogOptionExistsError):
        store.add_catalog_option(conn, "origen", "  PRESENCIAL ", NOW)


def test_add_catalog_option_marks_it_as_manual_and_active():
    conn = _conn()

    option = store.add_catalog_option(conn, "resultado", "ESCALADO", NOW)

    assert (option.category, option.value, option.active, option.source) == (
        "resultado",
        "ESCALADO",
        True,
        "manual",
    )


def test_set_catalog_option_active_returns_none_for_an_unknown_option():
    conn = _conn()

    assert store.set_catalog_option_active(conn, 999, False) is None
