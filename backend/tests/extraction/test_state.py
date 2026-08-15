import datetime
from pathlib import Path

import pytest

from app.c3 import downloads, massive
from app.extraction import service, state

_CYCLE = massive.CycleResult(action="triggered", name="attention", job_id=1)


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


def _fake_massive_run(ok: bool = True) -> service.MassiveRun:
    if not ok:
        return service.MassiveRun(massive=None, massive_error="boom")
    return service.MassiveRun(massive=_CYCLE, massive_error=None)


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
def reset_last_massive_run():
    state._last_massive_run = None
    yield
    state._last_massive_run = None


def test_run_massive_extraction_returns_a_summary_and_records_it_as_last_massive_run(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(service, "run_massive", lambda: _fake_massive_run(ok=True))

    summary = state.run_massive_extraction()

    assert summary.ok is True
    assert summary.massive == massive.describe(_CYCLE)
    assert summary.massive_error is None
    assert state.last_massive_run() == summary
    assert state.last_run() is None


def test_run_massive_extraction_reports_a_massive_error_and_ok_false(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(service, "run_massive", lambda: _fake_massive_run(ok=False))

    summary = state.run_massive_extraction()

    assert summary.ok is False
    assert summary.massive is None
    assert summary.massive_error == "boom"


def test_run_massive_extraction_raises_already_running_if_lock_held(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(service, "run_massive", lambda: _fake_massive_run(ok=True))
    state._lock.acquire()
    try:
        with pytest.raises(state.AlreadyRunningError):
            state.run_massive_extraction()
    finally:
        state._lock.release()


def test_run_massive_extraction_releases_the_lock_even_if_it_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    def boom():
        raise RuntimeError("login failed")

    monkeypatch.setattr(service, "run_massive", boom)

    with pytest.raises(RuntimeError):
        state.run_massive_extraction()

    assert not state._lock.locked()
    assert state.last_massive_run() is None


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
    assert state.last_massive_run() is None


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
    assert state.last_backfill_run() is None
