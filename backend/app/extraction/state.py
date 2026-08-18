import logging
import threading
from datetime import date, datetime

from .. import config
from ..schemas import (
    BackfillRunSummary,
    HistoricalBackfillStatus,
    HistoricalRunSummary,
    JobSummary,
    RunSummary,
)
from . import service

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_last_run: RunSummary | None = None
_last_backfill_run: BackfillRunSummary | None = None
_last_contacts_sync_run: RunSummary | None = None
_historical_backfill_status = HistoricalBackfillStatus()


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


def _log_job_outcomes(label: str, jobs: list[service.JobOutcome]) -> None:
    for outcome in jobs:
        if outcome.error:
            logger.warning("%s: '%s' fallo -- %s", label, outcome.job.name, outcome.error)
            continue

        if outcome.result is not None:
            logger.info(
                "%s: '%s' descarga ok (%d bytes, %.2fs)",
                label,
                outcome.job.name,
                outcome.result.size_bytes,
                outcome.result.elapsed_seconds,
            )

        if outcome.ingest_error:
            logger.warning(
                "%s: '%s' -> DB fallo el upsert -- %s",
                label,
                outcome.job.name,
                outcome.ingest_error,
            )
        elif outcome.ingest_result is not None:
            ir = outcome.ingest_result
            logger.info(
                "%s: '%s' -> DB %d vistas, %d insertadas/actualizadas, %d saltadas",
                label,
                outcome.job.name,
                ir.rows_seen,
                ir.rows_upserted,
                ir.rows_skipped,
            )


def run_extraction() -> RunSummary:
    global _last_run
    if not _lock.acquire(blocking=False):
        raise AlreadyRunningError("Ya hay una extraccion en curso.")
    logger.info("Refresh regular: iniciando")
    try:
        started_at = datetime.now(config.TZ)
        run = service.run()
    finally:
        _lock.release()

    _log_job_outcomes("Refresh regular", run.jobs)
    summary = RunSummary(
        started_at=started_at.isoformat(),
        finished_at=datetime.now(config.TZ).isoformat(),
        ok=run.ok,
        jobs=[_job_summary(o) for o in run.jobs],
    )
    _last_run = summary
    logger.info("Refresh regular: terminado (ok=%s)", summary.ok)
    return summary


def last_run() -> RunSummary | None:
    return _last_run


def run_backfill(target_date: date) -> BackfillRunSummary:
    global _last_backfill_run
    if not _lock.acquire(blocking=False):
        raise AlreadyRunningError("Ya hay una extraccion en curso.")
    logger.info("Backfill de %s: iniciando", target_date.isoformat())
    try:
        started_at = datetime.now(config.TZ)
        run = service.run_backfill(target_date)
    finally:
        _lock.release()

    label = f"Backfill de {target_date.isoformat()}"
    _log_job_outcomes(label, run.jobs)
    summary = BackfillRunSummary(
        started_at=started_at.isoformat(),
        finished_at=datetime.now(config.TZ).isoformat(),
        ok=run.ok,
        target_date=target_date.isoformat(),
        jobs=[_job_summary(o) for o in run.jobs],
    )
    _last_backfill_run = summary
    logger.info("%s: terminado (ok=%s)", label, summary.ok)
    return summary


def last_backfill_run() -> BackfillRunSummary | None:
    return _last_backfill_run


def run_contacts_sync() -> RunSummary:
    global _last_contacts_sync_run
    if not _lock.acquire(blocking=False):
        raise AlreadyRunningError("Ya hay una extraccion en curso.")
    logger.info("Sync de contactos: iniciando")
    try:
        started_at = datetime.now(config.TZ)
        run = service.run_contacts_sync()
    finally:
        _lock.release()

    _log_job_outcomes("Sync de contactos", run.jobs)
    summary = RunSummary(
        started_at=started_at.isoformat(),
        finished_at=datetime.now(config.TZ).isoformat(),
        ok=run.ok,
        jobs=[_job_summary(o) for o in run.jobs],
    )
    _last_contacts_sync_run = summary
    logger.info("Sync de contactos: terminado (ok=%s)", summary.ok)
    return summary


def last_contacts_sync_run() -> RunSummary | None:
    return _last_contacts_sync_run


def _run_historical_backfill_worker(started_at: str) -> None:
    global _historical_backfill_status
    logger.info(
        "Backfill historico: corriendo (ventana de %d dias)",
        config.HISTORICAL_BACKFILL_WINDOW_DAYS,
    )
    try:
        run = service.run_historical_backfill()
    except Exception as exc:
        logger.warning("Backfill historico: fallo antes de completar -- %s", exc)
        _historical_backfill_status = HistoricalBackfillStatus(
            phase="error",
            started_at=started_at,
            finished_at=datetime.now(config.TZ).isoformat(),
            error=str(exc),
        )
        _lock.release()
        return

    _log_job_outcomes("Backfill historico", run.jobs)

    finished_at = datetime.now(config.TZ).isoformat()
    _historical_backfill_status = HistoricalBackfillStatus(
        phase="done",
        started_at=started_at,
        finished_at=finished_at,
        result=HistoricalRunSummary(
            started_at=started_at,
            finished_at=finished_at,
            ok=run.ok,
            window_days=config.HISTORICAL_BACKFILL_WINDOW_DAYS,
            jobs=[_job_summary(o) for o in run.jobs],
        ),
    )
    logger.info("Backfill historico: terminado (ok=%s)", run.ok)
    _lock.release()


def start_historical_backfill() -> HistoricalBackfillStatus:
    global _historical_backfill_status
    if not _lock.acquire(blocking=False):
        raise AlreadyRunningError("Ya hay una extraccion en curso.")

    logger.info("Backfill historico: iniciando en background")
    started_at = datetime.now(config.TZ).isoformat()
    running_status = HistoricalBackfillStatus(phase="running", started_at=started_at)
    _historical_backfill_status = running_status
    threading.Thread(
        target=_run_historical_backfill_worker, args=(started_at,), daemon=True
    ).start()
    return running_status


def historical_backfill_status() -> HistoricalBackfillStatus:
    return _historical_backfill_status
