from dataclasses import dataclass

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


def run_all(client: httpx.Client) -> ExtractionRun:
    outcomes = []
    for job in downloads.build_jobs():
        try:
            result = downloads.run_job(client, job)
        except (downloads.DownloadError, httpx.HTTPError) as exc:
            outcomes.append(JobOutcome(job=job, result=None, error=str(exc)))
        else:
            outcomes.append(JobOutcome(job=job, result=result, error=None))

    return ExtractionRun(jobs=outcomes)


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
