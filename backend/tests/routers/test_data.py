import os
import sqlite3
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import config
from app.auth.dependencies import CurrentUser, get_current_user
from app.extraction import store


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "DOWNLOADS_DIR", tmp_path)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(1, "test", True)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _write_xlsx(path: Path, rows: list[tuple]) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def test_get_report_returns_parsed_rows(client: TestClient, tmp_path: Path):
    _write_xlsx(tmp_path / "attention_2026-08-13_export.xlsx", [("Nombre",), ("Ana",)])

    response = client.get("/data/attention")

    assert response.status_code == 200
    assert response.json() == [{"Nombre": "Ana"}]


def test_get_report_parses_csv_for_transfer(client: TestClient, tmp_path: Path):
    (tmp_path / "transfer_2026-08-17_Whatsapp_transferecias.csv").write_bytes(
        "﻿Nombre\r\nAna\r\n".encode("utf-8")
    )

    response = client.get("/data/transfer")

    assert response.status_code == 200
    assert response.json() == [{"Nombre": "Ana"}]


def test_get_report_404s_for_unknown_report_name(client: TestClient):
    response = client.get("/data/not-a-real-report")

    assert response.status_code == 404


def test_get_report_404s_when_nothing_downloaded_yet(client: TestClient):
    response = client.get("/data/contacts")

    assert response.status_code == 404


def test_get_report_page_returns_a_slice_and_the_total(
    client: TestClient, tmp_path: Path
):
    _write_xlsx(
        tmp_path / "attention_2026-08-13_export.xlsx",
        [("Nombre",), ("Ana",), ("Beto",), ("Caro",)],
    )

    response = client.get("/data/attention/page", params={"page": 2, "page_size": 2})

    assert response.status_code == 200
    assert response.json() == {"total": 3, "rows": [{"Nombre": "Caro"}]}


def test_get_report_page_defaults_to_the_first_page_of_fifty(
    client: TestClient, tmp_path: Path
):
    _write_xlsx(
        tmp_path / "attention_2026-08-13_export.xlsx",
        [("Nombre",), ("Ana",), ("Beto",)],
    )

    response = client.get("/data/attention/page")

    assert response.status_code == 200
    assert response.json() == {
        "total": 2,
        "rows": [{"Nombre": "Ana"}, {"Nombre": "Beto"}],
    }


def test_get_report_page_404s_for_unknown_report_name(client: TestClient):
    response = client.get("/data/not-a-real-report/page")

    assert response.status_code == 404


def test_get_report_page_404s_when_nothing_downloaded_yet(client: TestClient):
    response = client.get("/data/contacts/page")

    assert response.status_code == 404


def test_get_report_history_concatenates_every_downloaded_day_for_contacts(
    client: TestClient, tmp_path: Path
):
    older = tmp_path / "contacts_2026-08-13_export.xlsx"
    newer = tmp_path / "contacts_2026-08-14_export.xlsx"
    _write_xlsx(older, [("Nombre",), ("Ana",)])
    _write_xlsx(newer, [("Nombre",), ("Luis",)])
    older_time = newer.stat().st_mtime - 100
    os.utime(older, (older_time, older_time))

    response = client.get("/data/contacts/history")

    assert response.status_code == 200
    assert response.json() == [{"Nombre": "Ana"}, {"Nombre": "Luis"}]


def test_get_report_history_reads_dated_reports_from_the_store(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    store._init_schema(conn)
    store.upsert_report_rows(
        conn,
        "attention",
        [{"ID atención": "1", "Estado": "Abierta"}],
        observed_at="2026-08-13T00:00:00",
    )
    monkeypatch.setattr(store, "get_connection", lambda: conn)

    response = client.get("/data/attention/history")

    assert response.status_code == 200
    assert response.json() == [{"ID atención": "1", "Estado": "Abierta"}]


def test_get_report_history_filters_by_date_range_query_params(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    store._init_schema(conn)
    store.upsert_report_rows(
        conn,
        "attention",
        [
            {"ID atención": "in_range", "Fecha registro": "18/08/2026"},
            {"ID atención": "out_of_range", "Fecha registro": "01/09/2026"},
        ],
        observed_at="2026-08-19T00:00:00",
    )
    monkeypatch.setattr(store, "get_connection", lambda: conn)

    response = client.get(
        "/data/attention/history", params={"date_from": "2026-08-18", "date_to": "2026-08-18"}
    )

    assert response.status_code == 200
    assert [row["ID atención"] for row in response.json()] == ["in_range"]


def test_get_report_history_422s_for_malformed_date_from(client: TestClient):
    response = client.get("/data/attention/history", params={"date_from": "18-08-2026"})

    assert response.status_code == 422


def test_get_report_history_404s_for_unknown_report_name(client: TestClient):
    response = client.get("/data/not-a-real-report/history")

    assert response.status_code == 404


def test_get_report_history_404s_when_nothing_downloaded_yet(client: TestClient):
    response = client.get("/data/contacts/history")

    assert response.status_code == 404


def test_get_report_daily_counts_groups_rows_by_day(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    store._init_schema(conn)
    store.upsert_report_rows(
        conn,
        "attention",
        [
            {"ID atención": "1", "Fecha registro": "18/08/2026"},
            {"ID atención": "2", "Fecha registro": "18/08/2026"},
            {"ID atención": "3", "Fecha registro": "19/08/2026"},
        ],
        observed_at="2026-08-19T00:00:00",
    )
    monkeypatch.setattr(store, "get_connection", lambda: conn)

    response = client.get("/data/attention/history/daily-counts")

    assert response.status_code == 200
    assert response.json() == [
        {"date": "2026-08-18", "count": 2},
        {"date": "2026-08-19", "count": 1},
    ]


def test_get_report_daily_counts_filters_by_date_range_query_params(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    store._init_schema(conn)
    store.upsert_report_rows(
        conn,
        "attention",
        [
            {"ID atención": "in_range", "Fecha registro": "18/08/2026"},
            {"ID atención": "out_of_range", "Fecha registro": "01/09/2026"},
        ],
        observed_at="2026-08-19T00:00:00",
    )
    monkeypatch.setattr(store, "get_connection", lambda: conn)

    response = client.get(
        "/data/attention/history/daily-counts",
        params={"date_from": "2026-08-18", "date_to": "2026-08-18"},
    )

    assert response.status_code == 200
    assert response.json() == [{"date": "2026-08-18", "count": 1}]


def test_get_report_daily_counts_422s_for_malformed_date_from(client: TestClient):
    response = client.get(
        "/data/attention/history/daily-counts", params={"date_from": "18-08-2026"}
    )

    assert response.status_code == 422


def test_get_report_daily_counts_404s_for_unknown_report_name(client: TestClient):
    response = client.get("/data/not-a-real-report/history/daily-counts")

    assert response.status_code == 404


def test_get_report_daily_counts_404s_for_reports_without_a_date_column(client: TestClient):
    response = client.get("/data/contacts/history/daily-counts")

    assert response.status_code == 404


def test_get_report_daily_counts_filters_by_agentes_query_params(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    store._init_schema(conn)
    store.upsert_report_rows(
        conn,
        "attention",
        [
            {"ID atención": "ana", "Agente": "Ana", "Fecha registro": "18/08/2026"},
            {"ID atención": "bot", "Agente": "Bot", "Fecha registro": "18/08/2026"},
        ],
        observed_at="2026-08-19T00:00:00",
    )
    monkeypatch.setattr(store, "get_connection", lambda: conn)

    response = client.get(
        "/data/attention/history/daily-counts", params={"agentes": ["Ana"]}
    )

    assert response.status_code == 200
    assert response.json() == [{"date": "2026-08-18", "count": 1}]


def test_get_attention_records_returns_paginated_shape(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    store._init_schema(conn)
    store.upsert_report_rows(
        conn,
        "attention",
        [{"ID atención": "1", "Estado": "Abierta", "Agente": "Ana"}],
        observed_at="2026-08-19T00:00:00",
    )
    monkeypatch.setattr(store, "get_connection", lambda: conn)

    response = client.get("/data/attention-records")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["rows"][0]["direction"] == "incoming"
    assert body["rows"][0]["ID atención"] == "1"
    assert body["transfers"] == []
    assert "staleCount" in body


def test_get_attention_records_422s_for_invalid_direction(client: TestClient):
    response = client.get("/data/attention-records", params={"direction": "sideways"})

    assert response.status_code == 422


def test_get_attention_records_filters_by_query_params(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    store._init_schema(conn)
    store.upsert_report_rows(
        conn,
        "attention",
        [
            {"ID atención": "match", "Estado": "Abierta", "Agente": "Ana", "Campaña": "Soporte"},
            {"ID atención": "other", "Estado": "Cerrada", "Agente": "Luis", "Campaña": "Ventas"},
        ],
        observed_at="2026-08-19T00:00:00",
    )
    monkeypatch.setattr(store, "get_connection", lambda: conn)

    response = client.get(
        "/data/attention-records",
        params={"direction": "incoming", "estados": ["Abierta"], "campana": "Soporte"},
    )

    assert response.status_code == 200
    rows = response.json()["rows"]
    assert [row["ID atención"] for row in rows] == ["match"]
