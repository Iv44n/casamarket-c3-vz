import os
import sqlite3
from pathlib import Path

import openpyxl
import pytest

from app import config
from app.extraction import parsing, store


def _write_workbook(path: Path, sheets: dict[str, list[tuple]]) -> None:
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(title=name)
        for row in rows:
            sheet.append(row)
    workbook.save(path)


def test_parse_xlsx_concatenates_all_sheets(tmp_path: Path):
    path = tmp_path / "reporte.xlsx"
    _write_workbook(
        path,
        {
            "Campaña A": [("Nombre", "Estado"), ("Ana", "Abierta")],
            "Campaña B": [("Nombre", "Estado"), ("Luis", "Cerrada")],
        },
    )

    records = parsing.parse_xlsx(path)

    assert records == [
        {"Nombre": "Ana", "Estado": "Abierta"},
        {"Nombre": "Luis", "Estado": "Cerrada"},
    ]


def test_parse_xlsx_skips_sheets_without_a_header(tmp_path: Path):
    path = tmp_path / "reporte.xlsx"
    _write_workbook(
        path,
        {
            "Vacia": [],
            "Con datos": [("Nombre",), ("Ana",)],
        },
    )

    records = parsing.parse_xlsx(path)

    assert records == [{"Nombre": "Ana"}]


def test_parse_xlsx_skips_fully_empty_rows(tmp_path: Path):
    path = tmp_path / "reporte.xlsx"
    _write_workbook(
        path,
        {"Hoja": [("Nombre", "Estado"), ("Ana", "Abierta"), (None, None)]},
    )

    records = parsing.parse_xlsx(path)

    assert records == [{"Nombre": "Ana", "Estado": "Abierta"}]


def test_parse_csv_reads_utf8_bom_and_quoted_commas(tmp_path: Path):
    path = tmp_path / "reporte.csv"
    path.write_bytes(
        "﻿Nombre,Destino\r\nAna,\"CARLOS, GABRIEL\"\r\n".encode("utf-8")
    )

    assert parsing.parse_csv(path) == [{"Nombre": "Ana", "Destino": "CARLOS, GABRIEL"}]


def test_parse_report_dispatches_to_csv_by_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(config, "DOWNLOADS_DIR", tmp_path)
    (tmp_path / "transfer_2026-08-17_Whatsapp_transferecias.csv").write_bytes(
        "﻿Nombre\r\nAna\r\n".encode("utf-8")
    )

    assert parsing.parse_report("transfer") == [{"Nombre": "Ana"}]


def test_parse_report_returns_none_when_nothing_downloaded_yet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(config, "DOWNLOADS_DIR", tmp_path)

    assert parsing.parse_report("attention") is None


def test_parse_report_parses_the_latest_downloaded_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(config, "DOWNLOADS_DIR", tmp_path)
    _write_workbook(
        tmp_path / "attention_2026-08-13_export.xlsx",
        {"Campaña A": [("Nombre",), ("Ana",)]},
    )

    assert parsing.parse_report("attention") == [{"Nombre": "Ana"}]


def test_parse_report_history_returns_none_when_nothing_downloaded_yet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(config, "DOWNLOADS_DIR", tmp_path)

    assert parsing.parse_report_history("contacts") is None


def test_parse_report_history_reads_contacts_from_flat_files_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(config, "DOWNLOADS_DIR", tmp_path)
    older = tmp_path / "contacts_2026-08-13_export.xlsx"
    newer = tmp_path / "contacts_2026-08-14_export.xlsx"
    _write_workbook(older, {"Hoja": [("Nombre",), ("Ana",)]})
    _write_workbook(newer, {"Hoja": [("Nombre",), ("Luis",)]})
    older_time = newer.stat().st_mtime - 100
    os.utime(older, (older_time, older_time))

    assert parsing.parse_report_history("contacts") == [
        {"Nombre": "Ana"},
        {"Nombre": "Luis"},
    ]


def test_parse_report_history_reads_dated_reports_from_the_store(
    monkeypatch: pytest.MonkeyPatch,
):
    conn = sqlite3.connect(":memory:")
    store._init_schema(conn)
    store.upsert_report_rows(
        conn,
        "attention",
        [{"ID atención": "1", "Estado": "Abierta"}],
        observed_at="2026-08-13T00:00:00",
    )
    monkeypatch.setattr(store, "get_connection", lambda: conn)

    assert parsing.parse_report_history("attention") == [
        {"ID atención": "1", "Estado": "Abierta"}
    ]


def test_parse_report_history_forwards_a_date_range_to_the_store(
    monkeypatch: pytest.MonkeyPatch,
):
    conn = sqlite3.connect(":memory:")
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

    result = parsing.parse_report_history("attention", "2026-08-18", "2026-08-18")

    assert [row["ID atención"] for row in result] == ["in_range"]


def test_parse_report_history_returns_none_for_dated_reports_with_nothing_ingested(
    monkeypatch: pytest.MonkeyPatch,
):
    conn = sqlite3.connect(":memory:")
    store._init_schema(conn)
    monkeypatch.setattr(store, "get_connection", lambda: conn)

    assert parsing.parse_report_history("attention") is None
