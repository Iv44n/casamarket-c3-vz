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


class DailyCount(BaseModel):
    date: str
    count: int


class BenchmarkCaseResult(BaseModel):
    id_atencion: str
    direction: Literal["attention", "outboundattention"]
    agente: str | None
    campana: str | None
    estado: str | None
    fecha_final: str | None
    hora_final: str | None
    cliente: str | None
    first_response_seconds: float | None
    has_greeting: bool | None
    has_farewell: bool | None
    quality_ok: bool | None
    llm_notes: str | None
    analyzed_at: str | None


class BenchmarkDirectionSummary(BaseModel):
    direction: Literal["attention", "outboundattention"]
    action: Literal["analyzed", "failed"]
    cases_closed: int = 0
    cases_pending: int = 0
    cases_with_pdf: int = 0
    cases_analyzed: int = 0
    error: str | None = None


class BenchmarkRunSummary(BaseModel):
    started_at: str
    finished_at: str
    ok: bool
    directions: list[BenchmarkDirectionSummary]


class BenchmarkRunStatus(BaseModel):
    phase: Literal["idle", "running", "done", "error"] = "idle"
    started_at: str | None = None
    finished_at: str | None = None
    result: BenchmarkRunSummary | None = None
    error: str | None = None
