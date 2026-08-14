from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import config


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "DOWNLOADS_DIR", tmp_path)
    with TestClient(app) as c:
        yield c


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


def test_get_report_404s_for_unknown_report_name(client: TestClient):
    response = client.get("/data/not-a-real-report")

    assert response.status_code == 404


def test_get_report_404s_when_nothing_downloaded_yet(client: TestClient):
    response = client.get("/data/contacts")

    assert response.status_code == 404
