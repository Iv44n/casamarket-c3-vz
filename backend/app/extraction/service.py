from dataclasses import dataclass
from datetime import date, datetime

import httpx

from .. import config
from ..c3 import downloads, session
from . import parsing, store

_INGESTABLE_REPORTS = {"attention", "outboundattention", "callincoming", "calloutgoing", "transfer"}


@dataclass(frozen=True)
class JobOutcome:
    job: downloads.DownloadJob
    result: downloads.DownloadResult | None
    error: str | None
    ingest_result: store.IngestResult | None = None
    ingest_error: str | None = None


@dataclass(frozen=True)
class ExtractionRun:
    jobs: list[JobOutcome]

    @property
    def ok(self) -> bool:
        return all(j.error is None for j in self.jobs)


def _ingest_if_dated_report(
    conn: store.DBConnection, job: downloads.DownloadJob, result: downloads.DownloadResult
) -> tuple[store.IngestResult | None, str | None]:
    if job.name not in _INGESTABLE_REPORTS:
        return None, None
    try:
        rows = parsing.parse_path(result.path)
        observed_at = datetime.now(config.TZ).isoformat()
        ingest_result = store.upsert_report_rows(conn, job.name, rows, observed_at)
        return ingest_result, None
    except Exception as exc:
        return None, str(exc)


def _run_jobs(
    client: httpx.Client,
    jobs: list[downloads.DownloadJob],
    conn: store.DBConnection | None = None,
) -> ExtractionRun:
    owns_conn = conn is None
    if owns_conn:
        conn = store.get_connection()
    try:
        outcomes = []
        for job in jobs:
            try:
                result = downloads.run_job(client, job)
            except (downloads.DownloadError, httpx.HTTPError) as exc:
                outcomes.append(JobOutcome(job=job, result=None, error=str(exc)))
                continue

            ingest_result, ingest_error = _ingest_if_dated_report(conn, job, result)
            outcomes.append(
                JobOutcome(
                    job=job,
                    result=result,
                    error=None,
                    ingest_result=ingest_result,
                    ingest_error=ingest_error,
                )
            )

        return ExtractionRun(jobs=outcomes)
    finally:
        if owns_conn:
            conn.close()


def run_all(client: httpx.Client, conn: store.DBConnection | None = None) -> ExtractionRun:
    return _run_jobs(client, downloads.build_jobs(), conn=conn)


def run_backfill_jobs(
    client: httpx.Client, target_date: date, conn: store.DBConnection | None = None
) -> ExtractionRun:
    return _run_jobs(client, downloads.build_backfill_jobs(target_date), conn=conn)


def run_historical_jobs(
    client: httpx.Client,
    date_init: date,
    date_end: date,
    conn: store.DBConnection | None = None,
) -> ExtractionRun:
    owns_conn = conn is None
    if owns_conn:
        conn = store.get_connection()
    try:
        jobs = downloads.build_historical_jobs(date_init, date_end)
        observed_at = datetime.now(config.TZ).isoformat()
        outcomes = []
        for job in jobs:
            try:
                result = downloads.run_job(client, job)
            except (downloads.DownloadError, httpx.HTTPError) as exc:
                outcomes.append(JobOutcome(job=job, result=None, error=str(exc)))
                continue

            ingest_result = None
            ingest_error = None
            try:
                rows = parsing.parse_path(result.path)
                ingest_result = store.upsert_report_rows(conn, job.name, rows, observed_at)
            except Exception as exc:
                ingest_error = str(exc)
            outcomes.append(
                JobOutcome(
                    job=job,
                    result=result,
                    error=None,
                    ingest_result=ingest_result,
                    ingest_error=ingest_error,
                )
            )

        return ExtractionRun(jobs=outcomes)
    finally:
        if owns_conn:
            conn.close()


def run_contacts_sync_jobs(
    client: httpx.Client, conn: store.DBConnection | None = None
) -> ExtractionRun:
    """A diferencia de run_all()/run_backfill_jobs(), esto no descarga UN archivo -- el roster
    completo de una cuenta grande 500ea pedido de una sola vez (confirmado en vivo 2026-09-10
    contra salescasamarket.c3.pe), asi que build_contacts_sync_jobs() devuelve una ventana por
    ciertos dias (c3/downloads.py's _contacts_sync_jobs) que se fetchean EN MEMORIA (sin escribir
    a disco por ventana, ver fetch_window_bytes) y se van acumulando. Recien con todas las
    ventanas ya intentadas se escribe un unico archivo mergeado (write_merged_xlsx) y se inserta
    el snapshot completo en Turso -- si eso falla, la excepcion sube tal cual (el caller de mas
    arriba, extraction/state.py's worker en background, ya tiene su propio try/except para marcar
    el run como error, mismo patron que _run_historical_backfill_worker)."""
    owns_conn = conn is None
    if owns_conn:
        conn = store.get_connection()
    try:
        outcomes = []
        all_rows: list[dict] = []
        for job in downloads.build_contacts_sync_jobs():
            try:
                data, status_code, elapsed = downloads.fetch_window_bytes(client, job)
            except (downloads.DownloadError, httpx.HTTPError) as exc:
                outcomes.append(JobOutcome(job=job, result=None, error=str(exc)))
                continue

            result = downloads.DownloadResult(
                job=job,
                status_code=status_code,
                path=None,
                content_type=None,
                size_bytes=len(data),
                elapsed_seconds=elapsed,
            )
            try:
                # Una ventana con un .xlsx corrupto/inesperado es un fallo de PROCESAMIENTO,
                # no de descarga -- mismo error/ingest_error que _ingest_if_dated_report ya
                # distingue para los otros 4 reportes (error solo refleja el fetch; un
                # problema de parseo/DB no tira run.ok a False, solo se loguea). No aborta las
                # demas ventanas.
                window_rows = parsing.parse_xlsx_bytes(data)
            except Exception as exc:
                outcomes.append(
                    JobOutcome(job=job, result=result, error=None, ingest_error=str(exc))
                )
                continue

            all_rows.extend(window_rows)
            outcomes.append(JobOutcome(job=job, result=result, error=None))

        if all_rows:
            downloads.write_merged_xlsx(all_rows, config.hoy())
            captured_at = datetime.now(config.TZ).isoformat()
            store.insert_contacts_snapshot(conn, all_rows, captured_at)

        return ExtractionRun(jobs=outcomes)
    finally:
        if owns_conn:
            conn.close()


def run(
    creds: config.Credentials | None = None,
    transport: httpx.BaseTransport | None = None,
    conn: store.DBConnection | None = None,
) -> ExtractionRun:
    creds = creds or config.load_credentials()
    client = session.login(creds, transport=transport)
    try:
        return run_all(client, conn=conn)
    finally:
        client.close()


def run_backfill(
    target_date: date,
    creds: config.Credentials | None = None,
    transport: httpx.BaseTransport | None = None,
    conn: store.DBConnection | None = None,
) -> ExtractionRun:
    creds = creds or config.load_credentials()
    client = session.login(creds, transport=transport)
    try:
        return run_backfill_jobs(client, target_date, conn=conn)
    finally:
        client.close()


def run_contacts_sync(
    creds: config.Credentials | None = None,
    transport: httpx.BaseTransport | None = None,
    conn: store.DBConnection | None = None,
) -> ExtractionRun:
    creds = creds or config.load_credentials()
    client = session.login(creds, transport=transport)
    try:
        return run_contacts_sync_jobs(client, conn=conn)
    finally:
        client.close()


def run_historical_backfill(
    date_init: date,
    date_end: date,
    creds: config.Credentials | None = None,
    transport: httpx.BaseTransport | None = None,
    conn: store.DBConnection | None = None,
) -> ExtractionRun:
    creds = creds or config.load_credentials()
    client = session.login(
        creds, transport=transport, timeout=config.HISTORICAL_CLIENT_TIMEOUT_SECONDS
    )
    try:
        return run_historical_jobs(client, date_init, date_end, conn=conn)
    finally:
        client.close()
