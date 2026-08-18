import datetime

import pytest
from fastapi.testclient import TestClient

from app.extraction import state
from app.main import app
from app.schemas import (
    BackfillRunSummary,
    HistoricalBackfillStatus,
    HistoricalRunSummary,
    RunSummary,
)

_SUMMARY = RunSummary(
    started_at="2026-08-13T06:00:00-05:00",
    finished_at="2026-08-13T06:00:05-05:00",
    ok=True,
    jobs=[],
)

_BACKFILL_SUMMARY = BackfillRunSummary(
    started_at="2026-08-13T06:00:00-05:00",
    finished_at="2026-08-13T06:00:05-05:00",
    ok=True,
    target_date="2026-08-10",
    jobs=[],
)

_HISTORICAL_STATUS_RUNNING = HistoricalBackfillStatus(
    phase="running", started_at="2026-08-13T06:00:00-05:00"
)

_HISTORICAL_STATUS_DONE = HistoricalBackfillStatus(
    phase="done",
    started_at="2026-08-13T06:00:00-05:00",
    finished_at="2026-08-13T06:05:00-05:00",
    result=HistoricalRunSummary(
        started_at="2026-08-13T06:00:00-05:00",
        finished_at="2026-08-13T06:05:00-05:00",
        ok=True,
        date_init="2026-05-15",
        date_end="2026-08-13",
        jobs=[],
    ),
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


def test_backfill_returns_the_backfill_summary_and_passes_through_the_parsed_date(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    seen = []
    monkeypatch.setattr(
        state, "run_backfill", lambda target_date: (seen.append(target_date), _BACKFILL_SUMMARY)[1]
    )

    response = client.post("/extraction/backfill", json={"date": "2026-08-10"})

    assert response.status_code == 200
    assert response.json() == _BACKFILL_SUMMARY.model_dump()
    assert seen == [datetime.date(2026, 8, 10)]


def test_backfill_422s_on_a_malformed_date(client: TestClient):
    response = client.post("/extraction/backfill", json={"date": "not-a-date"})

    assert response.status_code == 422


def test_backfill_returns_409_when_already_running(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    def boom(target_date):
        raise state.AlreadyRunningError("ya hay una extraccion en curso")

    monkeypatch.setattr(state, "run_backfill", boom)

    response = client.post("/extraction/backfill", json={"date": "2026-08-10"})

    assert response.status_code == 409


def test_backfill_returns_502_on_auth_or_network_failure(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    def boom(target_date):
        raise RuntimeError("credenciales invalidas")

    monkeypatch.setattr(state, "run_backfill", boom)

    response = client.post("/extraction/backfill", json={"date": "2026-08-10"})

    assert response.status_code == 502


def test_backfill_status_returns_no_runs_yet_before_any_run(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    monkeypatch.setattr(state, "last_backfill_run", lambda: None)

    response = client.get("/extraction/backfill/status")

    assert response.json() == {"status": "no_runs_yet"}


def test_backfill_status_returns_the_last_backfill_run_summary(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    monkeypatch.setattr(state, "last_backfill_run", lambda: _BACKFILL_SUMMARY)

    response = client.get("/extraction/backfill/status")

    assert response.json() == _BACKFILL_SUMMARY.model_dump()


def test_contacts_sync_returns_the_run_summary(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    monkeypatch.setattr(state, "run_contacts_sync", lambda: _SUMMARY)

    response = client.post("/extraction/contacts/sync")

    assert response.status_code == 200
    assert response.json() == _SUMMARY.model_dump()


def test_contacts_sync_returns_409_when_already_running(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    def boom():
        raise state.AlreadyRunningError("ya hay una extraccion en curso")

    monkeypatch.setattr(state, "run_contacts_sync", boom)

    response = client.post("/extraction/contacts/sync")

    assert response.status_code == 409


def test_contacts_sync_returns_502_on_auth_or_network_failure(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    def boom():
        raise RuntimeError("credenciales invalidas")

    monkeypatch.setattr(state, "run_contacts_sync", boom)

    response = client.post("/extraction/contacts/sync")

    assert response.status_code == 502


def test_contacts_sync_status_returns_no_runs_yet_before_any_run(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    monkeypatch.setattr(state, "last_contacts_sync_run", lambda: None)

    response = client.get("/extraction/contacts/sync/status")

    assert response.json() == {"status": "no_runs_yet"}


def test_contacts_sync_status_returns_the_last_run_summary(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    monkeypatch.setattr(state, "last_contacts_sync_run", lambda: _SUMMARY)

    response = client.get("/extraction/contacts/sync/status")

    assert response.json() == _SUMMARY.model_dump()


def test_historical_backfill_returns_202_and_the_running_status(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    monkeypatch.setattr(
        state,
        "start_historical_backfill",
        lambda date_init=None, date_end=None: _HISTORICAL_STATUS_RUNNING,
    )

    response = client.post("/extraction/historical/backfill")

    assert response.status_code == 202
    assert response.json() == _HISTORICAL_STATUS_RUNNING.model_dump()


def test_historical_backfill_passes_through_a_custom_date_range(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    seen = []
    monkeypatch.setattr(
        state,
        "start_historical_backfill",
        lambda date_init=None, date_end=None: (
            seen.append((date_init, date_end)),
            _HISTORICAL_STATUS_RUNNING,
        )[1],
    )

    response = client.post(
        "/extraction/historical/backfill",
        json={"date_init": "2026-05-01", "date_end": "2026-06-01"},
    )

    assert response.status_code == 202
    assert seen == [(datetime.date(2026, 5, 1), datetime.date(2026, 6, 1))]


def test_historical_backfill_422s_when_date_init_is_after_date_end(
    client: TestClient,
):
    response = client.post(
        "/extraction/historical/backfill",
        json={"date_init": "2026-06-01", "date_end": "2026-05-01"},
    )

    assert response.status_code == 422


def test_historical_backfill_returns_409_when_already_running(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    def boom(date_init=None, date_end=None):
        raise state.AlreadyRunningError("ya hay una extraccion en curso")

    monkeypatch.setattr(state, "start_historical_backfill", boom)

    response = client.post("/extraction/historical/backfill")

    assert response.status_code == 409


def test_historical_backfill_status_returns_idle_before_any_run(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    monkeypatch.setattr(state, "historical_backfill_status", lambda: HistoricalBackfillStatus())

    response = client.get("/extraction/historical/backfill/status")

    assert response.json() == HistoricalBackfillStatus().model_dump()


def test_historical_backfill_status_returns_the_done_status(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
):
    monkeypatch.setattr(
        state, "historical_backfill_status", lambda: _HISTORICAL_STATUS_DONE
    )

    response = client.get("/extraction/historical/backfill/status")

    assert response.json() == _HISTORICAL_STATUS_DONE.model_dump()
