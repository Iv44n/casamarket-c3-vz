from datetime import date

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..extraction import state
from ..schemas import BackfillRunSummary, HistoricalBackfillStatus, NoRunsYet, RunSummary

router = APIRouter(prefix="/extraction", tags=["extraction"])


class BackfillRequest(BaseModel):
    date: date


class HistoricalBackfillRequest(BaseModel):
    date_init: date | None = None
    date_end: date | None = None


@router.post("/refresh")
def refresh() -> RunSummary:
    try:
        return state.run_extraction()
    except state.AlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/status")
def status() -> RunSummary | NoRunsYet:
    run = state.last_run()
    if run is None:
        return NoRunsYet()
    return run


@router.post("/backfill")
def backfill(request: BackfillRequest) -> BackfillRunSummary:
    try:
        return state.run_backfill(request.date)
    except state.AlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/backfill/status")
def backfill_status() -> BackfillRunSummary | NoRunsYet:
    run = state.last_backfill_run()
    if run is None:
        return NoRunsYet()
    return run


@router.post("/contacts/sync")
def contacts_sync() -> RunSummary:
    try:
        return state.run_contacts_sync()
    except state.AlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/contacts/sync/status")
def contacts_sync_status() -> RunSummary | NoRunsYet:
    run = state.last_contacts_sync_run()
    if run is None:
        return NoRunsYet()
    return run


@router.post("/historical/backfill", status_code=202)
def historical_backfill(
    request: HistoricalBackfillRequest | None = None,
) -> HistoricalBackfillStatus:
    date_init = request.date_init if request else None
    date_end = request.date_end if request else None
    if date_init is not None and date_end is not None and date_init > date_end:
        raise HTTPException(
            status_code=422, detail="date_init no puede ser posterior a date_end."
        )
    try:
        return state.start_historical_backfill(date_init=date_init, date_end=date_end)
    except state.AlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/historical/backfill/status")
def historical_backfill_status() -> HistoricalBackfillStatus:
    return state.historical_backfill_status()
