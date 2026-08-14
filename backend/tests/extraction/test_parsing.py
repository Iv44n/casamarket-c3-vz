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
