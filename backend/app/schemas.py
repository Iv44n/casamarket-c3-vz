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


class MassiveRunSummary(BaseModel):
    started_at: str
    finished_at: str
    ok: bool
    massive: str | None
    massive_error: str | None


class NoRunsYet(BaseModel):
    status: Literal["no_runs_yet"] = "no_runs_yet"
