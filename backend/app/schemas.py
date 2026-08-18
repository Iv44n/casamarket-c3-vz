from typing import Literal

from pydantic import BaseModel


class JobSummary(BaseModel):
    name: str
    ok: bool
    error: str | None
    size_bytes: int | None
    elapsed_seconds: float | None


class RunSummary(BaseModel):
    started_at: str
    finished_at: str
    ok: bool
    jobs: list[JobSummary]


class BackfillRunSummary(BaseModel):
    started_at: str
    finished_at: str
    ok: bool
    target_date: str
    jobs: list[JobSummary]


class HistoricalRunSummary(BaseModel):
    started_at: str
    finished_at: str
    ok: bool
    date_init: str
    date_end: str
    jobs: list[JobSummary]


class HistoricalBackfillStatus(BaseModel):
    phase: Literal["idle", "running", "done", "error"] = "idle"
    started_at: str | None = None
    finished_at: str | None = None
    result: HistoricalRunSummary | None = None
    error: str | None = None


class NoRunsYet(BaseModel):
    status: Literal["no_runs_yet"] = "no_runs_yet"
