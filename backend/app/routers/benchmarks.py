from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth.dependencies import get_current_user
from ..benchmarks import state
from ..extraction import store
from ..schemas import BenchmarkCaseResult, BenchmarkRunStatus

router = APIRouter(
    prefix="/benchmarks", tags=["benchmarks"], dependencies=[Depends(get_current_user)]
)

ISO_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


class BenchmarkRunRequest(BaseModel):
    directions: list[Literal["attention", "outboundattention"]] | None = None


@router.post("/run", status_code=202)
def run_benchmarks(request: BenchmarkRunRequest | None = None) -> BenchmarkRunStatus:
    try:
        return state.start_benchmark_run(request.directions if request else None)
    except state.AlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/run/status")
def run_status() -> BenchmarkRunStatus:
    return state.benchmark_run_status()


@router.get("/results")
def results(
    direction: Literal["attention", "outboundattention"] | None = Query(default=None),
    date_from: str | None = Query(default=None, pattern=ISO_DATE_PATTERN),
    date_to: str | None = Query(default=None, pattern=ISO_DATE_PATTERN),
) -> list[BenchmarkCaseResult]:
    conn = store.get_connection()
    try:
        rows = store.benchmark_result_rows(
            conn, direction=direction, date_from=date_from, date_to=date_to
        )
    finally:
        conn.close()
    return rows
