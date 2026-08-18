import datetime
import time
from pathlib import Path

import pytest

from app.c3 import downloads
from app.extraction import service, state, store
from app.schemas import HistoricalBackfillStatus


@pytest.fixture(autouse=True)
def reset_last_run():
    state._last_run = None
    yield
    state._last_run = None


def _fake_outcome(ok: bool) -> service.JobOutcome:
    job = downloads.DownloadJob(name="attention", endpoint="/fake", params={})
    if not ok:
        return service.JobOutcome(job=job, result=None, error="boom")
    result = downloads.DownloadResult(
        job=job,
        status_code=200,
        path=Path("attention_2026-08-13_export.xlsx"),
        content_type="application/vnd.ms-excel",
        size_bytes=1234,
        elapsed_seconds=0.42,
    )
    return service.JobOutcome(job=job, result=result, error=None)


def _fake_run(ok: bool = True) -> service.ExtractionRun:
    return service.ExtractionRun(jobs=[_fake_outcome(ok)])


def test_run_extraction_returns_a_summary_and_records_it_as_last_run(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(service, "run", lambda: _fake_run(ok=True))

    summary = state.run_extraction()

    assert summary.ok is True
    assert [job.model_dump() for job in summary.jobs] == [
        {
            "name": "attention",
            "ok": True,
            "error": None,
            "size_bytes": 1234,
            "elapsed_seconds": 0.42,
        }
    ]
    assert state.last_run() == summary


def test_run_extraction_reports_a_failed_job_and_ok_false(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(service, "run", lambda: _fake_run(ok=False))

    summary = state.run_extraction()

    assert summary.ok is False
    assert summary.jobs[0].error == "boom"


def test_run_extraction_logs_start_per_job_result_and_end(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.setattr(service, "run", lambda: _fake_run(ok=True))

    with caplog.at_level("INFO", logger="app.extraction.state"):
        state.run_extraction()

    messages = [r.getMessage() for r in caplog.records]
    assert any("Refresh regular: iniciando" in m for m in messages)
    assert any("attention" in m and "ok" in m for m in messages)
    assert any("Refresh regular: terminado (ok=True)" in m for m in messages)


def test_run_extraction_logs_a_warning_for_a_failed_job(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.setattr(service, "run", lambda: _fake_run(ok=False))

    with caplog.at_level("INFO", logger="app.extraction.state"):
        state.run_extraction()

    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("attention" in m and "boom" in m for m in warnings)


def test_run_extraction_raises_already_running_if_lock_held(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(service, "run", lambda: _fake_run(ok=True))
    state._lock.acquire()
    try:
        with pytest.raises(state.AlreadyRunningError):
            state.run_extraction()
    finally:
        state._lock.release()


def test_run_extraction_releases_the_lock_even_if_extraction_run_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    def boom():
        raise RuntimeError("login failed")

    monkeypatch.setattr(service, "run", boom)

    with pytest.raises(RuntimeError):
        state.run_extraction()

    assert not state._lock.locked()
    assert state.last_run() is None


@pytest.fixture(autouse=True)
def reset_last_backfill_run():
    state._last_backfill_run = None
    yield
    state._last_backfill_run = None


_TARGET_DATE = datetime.date(2026, 8, 10)


def test_run_backfill_returns_a_summary_with_the_target_date_and_records_it(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(service, "run_backfill", lambda target_date: _fake_run(ok=True))

    summary = state.run_backfill(_TARGET_DATE)

    assert summary.ok is True
    assert summary.target_date == "2026-08-10"
    assert state.last_backfill_run() == summary
    assert state.last_run() is None


def test_run_backfill_reports_a_failed_job_and_ok_false(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(service, "run_backfill", lambda target_date: _fake_run(ok=False))

    summary = state.run_backfill(_TARGET_DATE)

    assert summary.ok is False
    assert summary.jobs[0].error == "boom"


def test_run_backfill_raises_already_running_if_lock_held(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(service, "run_backfill", lambda target_date: _fake_run(ok=True))
    state._lock.acquire()
    try:
        with pytest.raises(state.AlreadyRunningError):
            state.run_backfill(_TARGET_DATE)
    finally:
        state._lock.release()


def test_run_backfill_releases_the_lock_even_if_it_raises(monkeypatch: pytest.MonkeyPatch):
    def boom(target_date):
        raise RuntimeError("login failed")

    monkeypatch.setattr(service, "run_backfill", boom)

    with pytest.raises(RuntimeError):
        state.run_backfill(_TARGET_DATE)

    assert not state._lock.locked()


@pytest.fixture(autouse=True)
def reset_last_contacts_sync_run():
    state._last_contacts_sync_run = None
    yield
    state._last_contacts_sync_run = None


def test_run_contacts_sync_returns_a_summary_and_records_it(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(service, "run_contacts_sync", lambda: _fake_run(ok=True))

    summary = state.run_contacts_sync()

    assert summary.ok is True
    assert state.last_contacts_sync_run() == summary
    assert state.last_run() is None
    assert state.last_backfill_run() is None


def test_run_contacts_sync_reports_a_failed_job_and_ok_false(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(service, "run_contacts_sync", lambda: _fake_run(ok=False))

    summary = state.run_contacts_sync()

    assert summary.ok is False
    assert summary.jobs[0].error == "boom"


def test_run_contacts_sync_logs_start_per_job_result_and_end(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.setattr(service, "run_contacts_sync", lambda: _fake_run(ok=True))

    with caplog.at_level("INFO", logger="app.extraction.state"):
        state.run_contacts_sync()

    messages = [r.getMessage() for r in caplog.records]
    assert any("Sync de contactos: iniciando" in m for m in messages)
    assert any("attention" in m and "ok" in m for m in messages)
    assert any("Sync de contactos: terminado (ok=True)" in m for m in messages)


def _fake_outcome_with_ingest(
    ingest_result: store.IngestResult | None = None, ingest_error: str | None = None
) -> service.JobOutcome:
    job = downloads.DownloadJob(name="contacts", endpoint="/fake", params={})
    result = downloads.DownloadResult(
        job=job,
        status_code=200,
        path=Path("contacts_2026-08-13_export.xlsx"),
        content_type="application/vnd.ms-excel",
        size_bytes=1234,
        elapsed_seconds=0.42,
    )
    return service.JobOutcome(
        job=job,
        result=result,
        error=None,
        ingest_result=ingest_result,
        ingest_error=ingest_error,
    )


def test_run_contacts_sync_logs_the_db_upsert_row_counts(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    ingest_result = store.IngestResult(
        report_name="contacts", rows_seen=100, rows_upserted=97, rows_skipped=3
    )
    outcome = _fake_outcome_with_ingest(ingest_result=ingest_result)
    monkeypatch.setattr(
        service, "run_contacts_sync", lambda: service.ExtractionRun(jobs=[outcome])
    )

    with caplog.at_level("INFO", logger="app.extraction.state"):
        state.run_contacts_sync()

    messages = [r.getMessage() for r in caplog.records]
    assert any(
        "-> DB" in m and "100 vistas" in m and "97 insertadas" in m and "3 saltadas" in m
        for m in messages
    )


def test_run_contacts_sync_logs_a_warning_when_the_db_upsert_fails(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    outcome = _fake_outcome_with_ingest(ingest_error="conexion a Turso rechazada")
    monkeypatch.setattr(
        service, "run_contacts_sync", lambda: service.ExtractionRun(jobs=[outcome])
    )

    with caplog.at_level("INFO", logger="app.extraction.state"):
        state.run_contacts_sync()

    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any(
        "-> DB fallo el upsert" in m and "conexion a Turso rechazada" in m
        for m in warnings
    )


def test_run_contacts_sync_raises_already_running_if_lock_held(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(service, "run_contacts_sync", lambda: _fake_run(ok=True))
    state._lock.acquire()
    try:
        with pytest.raises(state.AlreadyRunningError):
            state.run_contacts_sync()
    finally:
        state._lock.release()


def test_run_contacts_sync_releases_the_lock_even_if_it_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    def boom():
        raise RuntimeError("login failed")

    monkeypatch.setattr(service, "run_contacts_sync", boom)

    with pytest.raises(RuntimeError):
        state.run_contacts_sync()

    assert not state._lock.locked()
    assert state.last_contacts_sync_run() is None
    assert state.last_backfill_run() is None


@pytest.fixture(autouse=True)
def reset_historical_backfill_status():
    state._historical_backfill_status = HistoricalBackfillStatus()
    yield
    state._historical_backfill_status = HistoricalBackfillStatus()


def _wait_until_not_running(timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while state._historical_backfill_status.phase == "running":
        assert time.monotonic() < deadline, "el backfill en background nunca termino"
        time.sleep(0.01)


def test_start_historical_backfill_sets_phase_running_immediately(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(service, "run_historical_backfill", lambda: _fake_run(ok=True))

    status = state.start_historical_backfill()

    assert status.phase == "running"
    assert status.started_at is not None
    _wait_until_not_running()


def test_start_historical_backfill_eventually_reaches_done_with_the_summary(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(service, "run_historical_backfill", lambda: _fake_run(ok=True))

    state.start_historical_backfill()
    _wait_until_not_running()

    status = state.historical_backfill_status()
    assert status.phase == "done"
    assert status.result is not None
    assert status.result.ok is True
    assert status.result.window_days == 90
    assert not state._lock.locked()


def test_start_historical_backfill_logs_start_per_job_result_and_end(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    monkeypatch.setattr(service, "run_historical_backfill", lambda: _fake_run(ok=True))

    with caplog.at_level("INFO", logger="app.extraction.state"):
        state.start_historical_backfill()
        _wait_until_not_running()

    messages = [r.getMessage() for r in caplog.records]
    assert any("Backfill historico: iniciando en background" in m for m in messages)
    assert any("Backfill historico: corriendo" in m for m in messages)
    assert any("attention" in m and "ok" in m for m in messages)
    assert any("Backfill historico: terminado (ok=True)" in m for m in messages)


def test_start_historical_backfill_reaches_error_phase_if_service_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    def boom():
        raise RuntimeError("login failed")

    monkeypatch.setattr(service, "run_historical_backfill", boom)

    state.start_historical_backfill()
    _wait_until_not_running()

    status = state.historical_backfill_status()
    assert status.phase == "error"
    assert status.error == "login failed"
    assert not state._lock.locked()


def test_start_historical_backfill_raises_already_running_if_lock_held(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(service, "run_historical_backfill", lambda: _fake_run(ok=True))
    state._lock.acquire()
    try:
        with pytest.raises(state.AlreadyRunningError):
            state.start_historical_backfill()
    finally:
        state._lock.release()


def test_historical_backfill_status_defaults_to_idle():
    assert state.historical_backfill_status().phase == "idle"
