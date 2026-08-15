from dataclasses import dataclass
from datetime import date

import httpx

from .. import config
from ..c3 import downloads, massive, session


@dataclass(frozen=True)
class JobOutcome:
    job: downloads.DownloadJob
    result: downloads.DownloadResult | None
    error: str | None


@dataclass(frozen=True)
class ExtractionRun:
    jobs: list[JobOutcome]

    @property
    def ok(self) -> bool:
        return all(j.error is None for j in self.jobs)


@dataclass(frozen=True)
class MassiveRun:
    massive: massive.CycleResult | None
    massive_error: str | None

    @property
    def ok(self) -> bool:
        return self.massive_error is None


def _run_jobs(client: httpx.Client, jobs: list[downloads.DownloadJob]) -> ExtractionRun:
    outcomes = []
    for job in jobs:
        try:
            result = downloads.run_job(client, job)
        except (downloads.DownloadError, httpx.HTTPError) as exc:
            outcomes.append(JobOutcome(job=job, result=None, error=str(exc)))
        else:
            outcomes.append(JobOutcome(job=job, result=result, error=None))

    return ExtractionRun(jobs=outcomes)


def run_all(client: httpx.Client) -> ExtractionRun:
    return _run_jobs(client, downloads.build_jobs())


def run_backfill_jobs(client: httpx.Client, target_date: date) -> ExtractionRun:
    return _run_jobs(client, downloads.build_backfill_jobs(target_date))


def run_massive_cycle(client: httpx.Client) -> MassiveRun:
    try:
        return MassiveRun(massive=massive.run_cycle(client), massive_error=None)
    except (massive.MassiveError, httpx.HTTPError) as exc:
        return MassiveRun(massive=None, massive_error=str(exc))


def run(
    creds: config.Credentials | None = None,
    transport: httpx.BaseTransport | None = None,
) -> ExtractionRun:
    creds = creds or config.load_credentials()
    client = session.login(creds, transport=transport)
    try:
        return run_all(client)
    finally:
        client.close()


def run_massive(
    creds: config.Credentials | None = None,
    transport: httpx.BaseTransport | None = None,
) -> MassiveRun:
    creds = creds or config.load_credentials()
    client = session.login(creds, transport=transport)
    try:
        return run_massive_cycle(client)
    finally:
        client.close()


def run_backfill(
    target_date: date,
    creds: config.Credentials | None = None,
    transport: httpx.BaseTransport | None = None,
) -> ExtractionRun:
    creds = creds or config.load_credentials()
    client = session.login(creds, transport=transport)
    try:
        return run_backfill_jobs(client, target_date)
    finally:
        client.close()
