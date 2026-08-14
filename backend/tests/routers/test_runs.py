import pytest
from fastapi.testclient import TestClient

from app.extraction import state
from app.main import app
from app.schemas import MassiveRunSummary, RunSummary

_SUMMARY = RunSummary(
    started_at="2026-08-13T06:00:00-05:00",
    finished_at="2026-08-13T06:00:05-05:00",
    ok=True,
    jobs=[],
)

_MASSIVE_SUMMARY = MassiveRunSummary(
    started_at="2026-08-13T06:00:00-05:00",
    finished_at="2026-08-13T06:00:05-05:00",
    ok=True,
    massive="se encolo el reporte masivo de 'attention' (job #1)",
    massive_error=None,
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_refresh_returns_the_run_summary(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    monkeypatch.setattr(state, "run_extraction", lambda: _SUMMARY)

    response = client.post("/extraction/refresh")

    assert response.status_code == 200
    assert response.json() == _SUMMARY.model_dump()


def test_refresh_returns_409_when_already_running(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    def boom():
        raise state.AlreadyRunningError("ya hay una extraccion en curso")

    monkeypatch.setattr(state, "run_extraction", boom)

    response = client.post("/extraction/refresh")

    assert response.status_code == 409


def test_refresh_returns_502_on_auth_or_network_failure(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    def boom():
        raise RuntimeError("credenciales invalidas")

    monkeypatch.setattr(state, "run_extraction", boom)

    response = client.post("/extraction/refresh")

    assert response.status_code == 502


def test_status_returns_no_runs_yet_before_any_run(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    monkeypatch.setattr(state, "last_run", lambda: None)

    response = client.get("/extraction/status")

    assert response.json() == {"status": "no_runs_yet"}


def test_status_returns_the_last_run_summary(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    monkeypatch.setattr(state, "last_run", lambda: _SUMMARY)

    response = client.get("/extraction/status")

    assert response.json() == _SUMMARY.model_dump()


def test_massive_refresh_returns_the_massive_run_summary(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    monkeypatch.setattr(state, "run_massive_extraction", lambda: _MASSIVE_SUMMARY)

    response = client.post("/extraction/massive/refresh")

    assert response.status_code == 200
    assert response.json() == _MASSIVE_SUMMARY.model_dump()


def test_massive_refresh_returns_409_when_already_running(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    def boom():
        raise state.AlreadyRunningError("ya hay una extraccion en curso")

    monkeypatch.setattr(state, "run_massive_extraction", boom)

    response = client.post("/extraction/massive/refresh")

    assert response.status_code == 409


def test_massive_refresh_returns_502_on_auth_or_network_failure(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    def boom():
        raise RuntimeError("credenciales invalidas")

    monkeypatch.setattr(state, "run_massive_extraction", boom)

    response = client.post("/extraction/massive/refresh")

    assert response.status_code == 502


def test_massive_status_returns_no_runs_yet_before_any_run(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    monkeypatch.setattr(state, "last_massive_run", lambda: None)

    response = client.get("/extraction/massive/status")

    assert response.json() == {"status": "no_runs_yet"}


def test_massive_status_returns_the_last_massive_run_summary(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    monkeypatch.setattr(state, "last_massive_run", lambda: _MASSIVE_SUMMARY)

    response = client.get("/extraction/massive/status")

    assert response.json() == _MASSIVE_SUMMARY.model_dump()
