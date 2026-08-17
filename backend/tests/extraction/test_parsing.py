import os
from pathlib import Path

import openpyxl
import pytest

from app import config
from app.extraction import parsing


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

    assert parsing.parse_report_history("attention") is None


def test_parse_report_history_concatenates_every_days_file_oldest_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(config, "DOWNLOADS_DIR", tmp_path)
    older = tmp_path / "attention_2026-08-13_export.xlsx"
    newer = tmp_path / "attention_2026-08-14_export.xlsx"
    _write_workbook(older, {"Campaña A": [("Nombre",), ("Ana",)]})
    _write_workbook(newer, {"Campaña A": [("Nombre",), ("Luis",)]})
    older_time = newer.stat().st_mtime - 100
    os.utime(older, (older_time, older_time))

    assert parsing.parse_report_history("attention") == [
        {"Nombre": "Ana"},
        {"Nombre": "Luis"},
    ]
