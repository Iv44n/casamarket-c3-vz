import httpx
from fastapi import APIRouter, HTTPException

from ..extraction import state
from ..schemas import MassiveRunSummary, NoRunsYet, RunSummary

router = APIRouter(prefix="/extraction", tags=["extraction"])


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


@router.post("/massive/refresh")
def massive_refresh() -> MassiveRunSummary:
    try:
        return state.run_massive_extraction()
    except state.AlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/massive/status")
def massive_status() -> MassiveRunSummary | NoRunsYet:
    run = state.last_massive_run()
    if run is None:
        return NoRunsYet()
    return run
