import pytest

from app.extraction import store as extraction_store
from app.incidents import store as incidents_store

_CATALOG = {
    "origen": ["ADMIN WEB"],
    "tipo": ["CONSULTAS"],
    "ambito": ["VENTAS", "CAJA"],
    "resultado": ["RESUELTO"],
}

_BODY = {
    "fecha": "2026-11-09",
    "hora": "10:30",
    "cliente": "Bodega Uno",
    "telefono": "999000111",
    "agente": "Ana",
    "origen": "ADMIN WEB",
    "tipo": "CONSULTAS",
    "ambito": "VENTAS",
    "resultado": "RESUELTO",
    "descripcion": "No puede emitir boletas",
}


@pytest.fixture
def seeded(api):
    conn = incidents_store.get_connection()
    incidents_store.import_catalog_values(conn, _CATALOG, "2026-11-09T00:00:00")
    conn.close()
    return api


def _range(day: str = "2026-11-09") -> dict:
    return {"date_from": day, "date_to": day}


def test_incidents_role_can_create_list_update_and_delete(seeded):
    headers = seeded.user_headers("rosa", "incidencias")

    created = seeded.client.post("/incidents", json=_BODY, headers=headers)
    assert created.status_code == 201
    incident = created.json()
    assert incident["created_by"] == "rosa"

    listed = seeded.client.get("/incidents", params=_range(), headers=headers)
    assert listed.status_code == 200
    assert [r["id"] for r in listed.json()["rows"]] == [incident["id"]]
    assert listed.json()["truncated"] is False

    updated = seeded.client.put(
        f"/incidents/{incident['id']}",
        json={**_BODY, "ambito": "CAJA", "descripcion": "Ahora es de caja"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["ambito"] == "CAJA"
    assert updated.json()["updated_by"] == "rosa"

    deleted = seeded.client.delete(f"/incidents/{incident['id']}", headers=headers)
    assert deleted.status_code == 204
    assert seeded.client.get("/incidents", params=_range(), headers=headers).json()["rows"] == []


def test_any_incidents_user_can_edit_incidents_created_by_someone_else(seeded):
    rosa = seeded.user_headers("rosa", "incidencias")
    luis = seeded.user_headers("luis", "incidencias")
    incident = seeded.client.post("/incidents", json=_BODY, headers=rosa).json()

    response = seeded.client.put(
        f"/incidents/{incident['id']}", json={**_BODY, "descripcion": "x"}, headers=luis
    )

    assert response.status_code == 200
    assert response.json()["created_by"] == "rosa"
    assert response.json()["updated_by"] == "luis"


def test_create_rejects_a_value_outside_the_catalog_with_422(seeded):
    headers = seeded.user_headers("rosa", "incidencias")

    response = seeded.client.post(
        "/incidents", json={**_BODY, "origen": "INVENTADO"}, headers=headers
    )

    assert response.status_code == 422
    assert "origen" in response.json()["detail"]


@pytest.mark.parametrize(
    "override",
    [
        {"fecha": "2026-13-45"},
        {"fecha": "09/11/2026"},
        {"hora": "25:00"},
        {"descripcion": "   "},
        {"origen": ""},
    ],
)
def test_create_validates_the_request_body(seeded, override: dict):
    headers = seeded.user_headers("rosa", "incidencias")

    response = seeded.client.post("/incidents", json={**_BODY, **override}, headers=headers)

    assert response.status_code == 422


def test_create_accepts_an_empty_hora_and_resultado(seeded):
    headers = seeded.user_headers("rosa", "incidencias")

    response = seeded.client.post(
        "/incidents", json={**_BODY, "hora": "", "resultado": ""}, headers=headers
    )

    assert response.status_code == 201


def test_create_accepts_an_empty_phone(seeded):
    headers = seeded.user_headers("rosa", "incidencias")

    response = seeded.client.post(
        "/incidents", json={**_BODY, "telefono": ""}, headers=headers
    )

    assert response.status_code == 201
    assert response.json()["telefono"] == ""


def test_update_and_delete_return_404_for_an_unknown_incident(seeded):
    headers = seeded.user_headers("rosa", "incidencias")

    assert seeded.client.put("/incidents/999", json=_BODY, headers=headers).status_code == 404
    assert seeded.client.delete("/incidents/999", headers=headers).status_code == 404


def test_list_rejects_an_inverted_date_range(seeded):
    headers = seeded.user_headers("rosa", "incidencias")

    response = seeded.client.get(
        "/incidents", params={"date_from": "2026-11-10", "date_to": "2026-11-09"}, headers=headers
    )

    assert response.status_code == 422


def test_export_returns_every_field_of_the_range(seeded):
    headers = seeded.user_headers("rosa", "incidencias")
    created = seeded.client.post("/incidents", json=_BODY, headers=headers).json()
    seeded.client.post("/incidents", json={**_BODY, "fecha": "2026-11-20"}, headers=headers)

    response = seeded.client.get("/incidents/export", params=_range(), headers=headers)

    assert response.status_code == 200
    assert response.json() == [created]


def test_export_rejects_an_inverted_date_range(seeded):
    headers = seeded.user_headers("rosa", "incidencias")

    response = seeded.client.get(
        "/incidents/export",
        params={"date_from": "2026-11-10", "date_to": "2026-11-09"},
        headers=headers,
    )

    assert response.status_code == 422


def test_list_requires_a_date_range(seeded):
    headers = seeded.user_headers("rosa", "incidencias")

    assert seeded.client.get("/incidents", headers=headers).status_code == 422


def test_every_role_can_read_the_catalog(seeded):
    headers = seeded.user_headers("rosa", "incidencias")

    response = seeded.client.get("/incidents/catalog", headers=headers)

    assert response.status_code == 200
    assert {(o["category"], o["value"]) for o in response.json()} == {
        (category, value) for category, values in _CATALOG.items() for value in values
    }


@pytest.mark.parametrize("role", ["user", "incidencias"])
def test_catalog_writes_require_admin(seeded, role: str):
    headers = seeded.user_headers("ana", role)
    option_id = seeded.client.get("/incidents/catalog", headers=headers).json()[0]["id"]

    assert (
        seeded.client.post(
            "/incidents/catalog", json={"category": "origen", "value": "X"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        seeded.client.patch(
            f"/incidents/catalog/{option_id}", json={"active": False}, headers=headers
        ).status_code
        == 403
    )
    assert seeded.client.post("/incidents/catalog/import-c3", headers=headers).status_code == 403


def test_admin_can_add_and_deactivate_catalog_options(seeded):
    headers = seeded.user_headers("boss", "admin")

    added = seeded.client.post(
        "/incidents/catalog", json={"category": "origen", "value": " PRESENCIAL "}, headers=headers
    )
    duplicate = seeded.client.post(
        "/incidents/catalog", json={"category": "origen", "value": "PRESENCIAL"}, headers=headers
    )
    deactivated = seeded.client.patch(
        f"/incidents/catalog/{added.json()['id']}", json={"active": False}, headers=headers
    )

    assert added.status_code == 201
    assert added.json()["value"] == "PRESENCIAL"
    assert added.json()["source"] == "manual"
    assert duplicate.status_code == 409
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False
    assert (
        seeded.client.patch(
            "/incidents/catalog/999", json={"active": True}, headers=headers
        ).status_code
        == 404
    )


def test_admin_import_from_c3_adds_only_new_values(seeded, monkeypatch: pytest.MonkeyPatch):
    class _FakeConn:
        def close(self) -> None:
            pass

    monkeypatch.setattr(extraction_store, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(
        extraction_store,
        "distinct_incident_values",
        lambda conn: {**_CATALOG, "ambito": ["VENTAS", "CAJA", "KARDEX"]},
    )
    headers = seeded.user_headers("boss", "admin")

    response = seeded.client.post("/incidents/catalog/import-c3", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"added": 1}
