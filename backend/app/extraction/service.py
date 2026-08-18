from dataclasses import dataclass
from datetime import date, datetime, timedelta

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
                if job.name == "contacts":
                    ingest_result = store.insert_contacts_snapshot(conn, rows, observed_at)
                else:
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
    owns_conn = conn is None
    if owns_conn:
        conn = store.get_connection()
    try:
        outcomes = []
        for job in downloads.build_contacts_sync_jobs():
            try:
                result = downloads.run_job(client, job)
            except (downloads.DownloadError, httpx.HTTPError) as exc:
                outcomes.append(JobOutcome(job=job, result=None, error=str(exc)))
                continue

            ingest_result = None
            ingest_error = None
            try:
                rows = parsing.parse_path(result.path)
                captured_at = datetime.now(config.TZ).isoformat()
                ingest_result = store.insert_contacts_snapshot(conn, rows, captured_at)
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
    creds: config.Credentials | None = None,
    transport: httpx.BaseTransport | None = None,
    window_days: int = config.HISTORICAL_BACKFILL_WINDOW_DAYS,
    conn: store.DBConnection | None = None,
) -> ExtractionRun:
    creds = creds or config.load_credentials()
    client = session.login(
        creds, transport=transport, timeout=config.HISTORICAL_CLIENT_TIMEOUT_SECONDS
    )
    try:
        date_end = config.hoy()
        date_init = date_end - timedelta(days=window_days)
        return run_historical_jobs(client, date_init, date_end, conn=conn)
    finally:
        client.close()
