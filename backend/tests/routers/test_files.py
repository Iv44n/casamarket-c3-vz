from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "DOWNLOADS_DIR", tmp_path)
    with TestClient(app) as c:
        yield c


def test_list_files_returns_empty_when_nothing_downloaded_yet(client: TestClient):
    response = client.get("/extraction/files")

    assert response.status_code == 200
    assert response.json() == []


def test_list_files_returns_known_reports_sorted_by_name_then_date(
    client: TestClient, tmp_path: Path
):
    (tmp_path / "attention_2026-08-14_export.xlsx").write_bytes(b"xx")
    (tmp_path / "attention_2026-08-13_export.xlsx").write_bytes(b"x")
    (tmp_path / "contacts_2026-08-13_export.xlsx").write_bytes(b"xxx")

    response = client.get("/extraction/files")

    assert response.status_code == 200
    assert response.json() == [
        {
            "report_name": "attention",
            "date": "2026-08-13",
            "filename": "attention_2026-08-13_export.xlsx",
            "size_bytes": 1,
        },
        {
            "report_name": "attention",
            "date": "2026-08-14",
            "filename": "attention_2026-08-14_export.xlsx",
            "size_bytes": 2,
        },
        {
            "report_name": "contacts",
            "date": "2026-08-13",
            "filename": "contacts_2026-08-13_export.xlsx",
            "size_bytes": 3,
        },
    ]


def test_list_files_includes_massive_zip_downloads(
    client: TestClient, tmp_path: Path
):
    (tmp_path / "attention_masivo_2026-08-13_export.zip").write_bytes(b"x")

    response = client.get("/extraction/files")

    assert response.status_code == 200
    assert response.json() == [
        {
            "report_name": "attention",
            "date": "2026-08-13",
            "filename": "attention_masivo_2026-08-13_export.zip",
            "size_bytes": 1,
        }
    ]


def test_list_files_ignores_unrelated_files(client: TestClient, tmp_path: Path):
    (tmp_path / ".~lock.attention_2026-08-14_export.xlsx#").write_bytes(b"x")
    (tmp_path / "not-a-report_2026-08-13_export.xlsx").write_bytes(b"x")

    response = client.get("/extraction/files")

    assert response.status_code == 200
    assert response.json() == []


def test_download_file_returns_its_bytes(client: TestClient, tmp_path: Path):
    path = tmp_path / "attention_2026-08-13_export.xlsx"
    path.write_bytes(b"fake xlsx contents")

    response = client.get("/extraction/files/attention_2026-08-13_export.xlsx")

    assert response.status_code == 200
    assert response.content == b"fake xlsx contents"
    assert "attention_2026-08-13_export.xlsx" in response.headers["content-disposition"]


def test_download_file_404s_when_file_does_not_exist(client: TestClient):
    response = client.get("/extraction/files/attention_2026-08-13_export.xlsx")

    assert response.status_code == 404


def test_download_file_400s_for_a_name_not_matching_the_download_convention(
    client: TestClient, tmp_path: Path
):
    (tmp_path / "not-a-report_2026-08-13_export.xlsx").write_bytes(b"x")

    response = client.get("/extraction/files/not-a-report_2026-08-13_export.xlsx")

    assert response.status_code == 400


def test_download_file_rejects_a_path_traversal_attempt(client: TestClient):
    response = client.get(
        "/extraction/files/attention_2026-08-13_..%2F..%2F..%2Fetc%2Fpasswd"
    )

    assert response.status_code == 404


def test_delete_file_removes_it_and_it_no_longer_lists(
    client: TestClient, tmp_path: Path
):
    path = tmp_path / "attention_2026-08-13_export.xlsx"
    path.write_bytes(b"x")

    response = client.delete("/extraction/files/attention_2026-08-13_export.xlsx")

    assert response.status_code == 200
    assert not path.exists()
    assert client.get("/extraction/files").json() == []


def test_delete_file_404s_when_file_does_not_exist(client: TestClient):
    response = client.delete("/extraction/files/attention_2026-08-13_export.xlsx")

    assert response.status_code == 404


def test_delete_file_400s_for_a_name_not_matching_the_download_convention(
    client: TestClient, tmp_path: Path
):
    (tmp_path / "not-a-report_2026-08-13_export.xlsx").write_bytes(b"x")

    response = client.delete("/extraction/files/not-a-report_2026-08-13_export.xlsx")

    assert response.status_code == 400


def test_delete_file_rejects_a_path_traversal_attempt(client: TestClient):
    response = client.delete(
        "/extraction/files/attention_2026-08-13_..%2F..%2F..%2Fetc%2Fpasswd"
    )

    assert response.status_code == 404
