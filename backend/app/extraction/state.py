import logging
import threading
from datetime import date, datetime, timedelta

from .. import config
from ..schemas import (
    BackfillRunSummary,
    HistoricalBackfillStatus,
    HistoricalRunSummary,
    JobSummary,
    RunSummary,
)
from . import service, store

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_historical_lock = threading.Lock()
_last_run: RunSummary | None = None
_last_backfill_run: BackfillRunSummary | None = None
_last_contacts_sync_run: RunSummary | None = None
_historical_backfill_status = HistoricalBackfillStatus()

_KIND_LAST_RUN = "last_run"
_KIND_LAST_BACKFILL_RUN = "last_backfill_run"
_KIND_LAST_CONTACTS_SYNC_RUN = "last_contacts_sync_run"
_KIND_HISTORICAL_BACKFILL_STATUS = "historical_backfill_status"

_hydrated_kinds: set[str] = set()


def _persist_sync_status(kind: str, status) -> None:
    try:
        conn = store.get_connection()
        try:
            store.save_sync_status(
                conn,
                kind,
                status.model_dump(mode="json"),
                datetime.now(config.TZ).isoformat(),
            )
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("No se pudo persistir el estado '%s' en la DB -- %s", kind, exc)


def _hydrate_once(kind: str, model):
    if kind in _hydrated_kinds:
        return None
    _hydrated_kinds.add(kind)
    try:
        conn = store.get_connection()
        try:
            data = store.load_sync_status(conn, kind)
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("No se pudo leer el estado '%s' desde la DB -- %s", kind, exc)
        return None
    if data is None:
        return None
    try:
        return model.model_validate(data)
    except Exception as exc:
        logger.warning("Estado '%s' guardado en la DB tiene forma invalida -- %s", kind, exc)
        return None


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
    _persist_sync_status(_KIND_LAST_RUN, summary)
    logger.info("Refresh regular: terminado (ok=%s)", summary.ok)
    return summary


def last_run() -> RunSummary | None:
    global _last_run
    if _last_run is None:
        loaded = _hydrate_once(_KIND_LAST_RUN, RunSummary)
        if loaded is not None:
            _last_run = loaded
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
    _persist_sync_status(_KIND_LAST_BACKFILL_RUN, summary)
    logger.info("%s: terminado (ok=%s)", label, summary.ok)
    return summary


def last_backfill_run() -> BackfillRunSummary | None:
    global _last_backfill_run
    if _last_backfill_run is None:
        loaded = _hydrate_once(_KIND_LAST_BACKFILL_RUN, BackfillRunSummary)
        if loaded is not None:
            _last_backfill_run = loaded
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
    _persist_sync_status(_KIND_LAST_CONTACTS_SYNC_RUN, summary)
    logger.info("Sync de contactos: terminado (ok=%s)", summary.ok)
    return summary


def last_contacts_sync_run() -> RunSummary | None:
    global _last_contacts_sync_run
    if _last_contacts_sync_run is None:
        loaded = _hydrate_once(_KIND_LAST_CONTACTS_SYNC_RUN, RunSummary)
        if loaded is not None:
            _last_contacts_sync_run = loaded
    return _last_contacts_sync_run


def _run_historical_backfill_worker(
    started_at: str, date_init: date, date_end: date
) -> None:
    global _historical_backfill_status
    logger.info(
        "Backfill historico: corriendo (%s a %s)",
        date_init.isoformat(),
        date_end.isoformat(),
    )
    try:
        run = service.run_historical_backfill(date_init, date_end)
    except Exception as exc:
        logger.warning("Backfill historico: fallo antes de completar -- %s", exc)
        error_status = HistoricalBackfillStatus(
            phase="error",
            started_at=started_at,
            finished_at=datetime.now(config.TZ).isoformat(),
            error=str(exc),
        )
        _persist_sync_status(_KIND_HISTORICAL_BACKFILL_STATUS, error_status)
        # el flip del global va al final -- es la señal que polling externo (incluida
        # `_wait_until_not_running` en los tests) usa para saber que ya no hay nada mas
        # pendiente, persistencia incluida.
        _historical_backfill_status = error_status
        _historical_lock.release()
        return

    _log_job_outcomes("Backfill historico", run.jobs)

    finished_at = datetime.now(config.TZ).isoformat()
    done_status = HistoricalBackfillStatus(
        phase="done",
        started_at=started_at,
        finished_at=finished_at,
        result=HistoricalRunSummary(
            started_at=started_at,
            finished_at=finished_at,
            ok=run.ok,
            date_init=date_init.isoformat(),
            date_end=date_end.isoformat(),
            jobs=[_job_summary(o) for o in run.jobs],
        ),
    )
    _persist_sync_status(_KIND_HISTORICAL_BACKFILL_STATUS, done_status)
    logger.info("Backfill historico: terminado (ok=%s)", run.ok)
    _historical_backfill_status = done_status
    _historical_lock.release()


def start_historical_backfill(
    date_init: date | None = None, date_end: date | None = None
) -> HistoricalBackfillStatus:
    global _historical_backfill_status
    # _historical_lock (separado de _lock) para que el backfill historico -- que
    # corre en background y puede tardar minutos -- NO bloquee los refreshes
    # regulares de cada 5 min. Es seguro correrlos en paralelo: cada run crea su
    # propio httpx.Client (sesion C3 independiente) y los upserts a Turso son
    # idempotentes por PK. Solo queremos evitar dos backfills historicos
    # solapados.
    if not _historical_lock.acquire(blocking=False):
        raise AlreadyRunningError("Ya hay un backfill historico en curso.")

    resolved_end = date_end or config.hoy()
    resolved_init = date_init or (
        resolved_end - timedelta(days=config.HISTORICAL_BACKFILL_WINDOW_DAYS)
    )

    logger.info(
        "Backfill historico: iniciando en background (%s a %s)",
        resolved_init.isoformat(),
        resolved_end.isoformat(),
    )
    started_at = datetime.now(config.TZ).isoformat()
    running_status = HistoricalBackfillStatus(phase="running", started_at=started_at)
    _historical_backfill_status = running_status
    _persist_sync_status(_KIND_HISTORICAL_BACKFILL_STATUS, running_status)
    threading.Thread(
        target=_run_historical_backfill_worker,
        args=(started_at, resolved_init, resolved_end),
        daemon=True,
    ).start()
    return running_status


def historical_backfill_status() -> HistoricalBackfillStatus:
    global _historical_backfill_status
    if _historical_backfill_status.phase == "idle":
        loaded = _hydrate_once(_KIND_HISTORICAL_BACKFILL_STATUS, HistoricalBackfillStatus)
        if loaded is not None:
            _historical_backfill_status = loaded
    return _historical_backfill_status
