import threading
from datetime import date, datetime

from .. import config
from ..c3 import massive
from ..schemas import BackfillRunSummary, JobSummary, MassiveRunSummary, RunSummary
from . import service

_lock = threading.Lock()
_last_run: RunSummary | None = None
_last_massive_run: MassiveRunSummary | None = None
_last_backfill_run: BackfillRunSummary | None = None


class AlreadyRunningError(RuntimeError):
    pass


def _job_summary(outcome: service.JobOutcome) -> JobSummary:
    result = outcome.result
    return JobSummary(
        name=outcome.job.name,
        ok=outcome.error is None,
        error=outcome.error,
        size_bytes=result.size_bytes if result else None,
        elapsed_seconds=result.elapsed_seconds if result else None,
    )


def run_extraction() -> RunSummary:
    global _last_run
    if not _lock.acquire(blocking=False):
        raise AlreadyRunningError("Ya hay una extraccion en curso.")
    try:
        started_at = datetime.now(config.TZ)
        run = service.run()
    finally:
        _lock.release()

    summary = RunSummary(
        started_at=started_at.isoformat(),
        finished_at=datetime.now(config.TZ).isoformat(),
        ok=run.ok,
        jobs=[_job_summary(o) for o in run.jobs],
    )
    _last_run = summary
    return summary


def last_run() -> RunSummary | None:
    return _last_run


def run_massive_extraction() -> MassiveRunSummary:
    global _last_massive_run
    if not _lock.acquire(blocking=False):
        raise AlreadyRunningError("Ya hay una extraccion en curso.")
    try:
        started_at = datetime.now(config.TZ)
        run = service.run_massive()
    finally:
        _lock.release()

    summary = MassiveRunSummary(
        started_at=started_at.isoformat(),
        finished_at=datetime.now(config.TZ).isoformat(),
        ok=run.ok,
        massive=massive.describe(run.massive) if run.massive else None,
        massive_error=run.massive_error,
    )
    _last_massive_run = summary
    return summary


def last_massive_run() -> MassiveRunSummary | None:
    return _last_massive_run


def run_backfill(target_date: date) -> BackfillRunSummary:
    global _last_backfill_run
    if not _lock.acquire(blocking=False):
        raise AlreadyRunningError("Ya hay una extraccion en curso.")
    try:
        started_at = datetime.now(config.TZ)
        run = service.run_backfill(target_date)
    finally:
        _lock.release()

    summary = BackfillRunSummary(
        started_at=started_at.isoformat(),
        finished_at=datetime.now(config.TZ).isoformat(),
        ok=run.ok,
        target_date=target_date.isoformat(),
        jobs=[_job_summary(o) for o in run.jobs],
    )
    _last_backfill_run = summary
    return summary


def last_backfill_run() -> BackfillRunSummary | None:
    return _last_backfill_run
