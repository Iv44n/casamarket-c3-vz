from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth.dependencies import CurrentUser, get_current_user, require_admin
from ..benchmarks import settings as llm_settings
from ..benchmarks import state
from ..extraction import store
from ..schemas import BenchmarkCaseResult, BenchmarkRunRecord, BenchmarkRunStatus

router = APIRouter(
    prefix="/benchmarks", tags=["benchmarks"], dependencies=[Depends(get_current_user)]
)

ISO_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


class BenchmarkRunRequest(BaseModel):
    directions: list[Literal["attention", "outboundattention"]] | None = None
    # Acotan que casos locales se consideran candidatos -- pensados para venir del mismo
    # filtro de fecha compartido que ya usa GET /benchmarks/results en el frontend. OJO: el
    # reporte masivo de C3 (la fuente de los PDFs a analizar) sigue devolviendo siempre el zip
    # de HOY -- un rango que no incluya hoy no va a conseguir PDFs nuevos para esos casos (ver
    # pipeline.analyze_direction). Field (no Query) porque esto es un modelo de body, no
    # parametros de query string.
    date_from: str | None = Field(default=None, pattern=ISO_DATE_PATTERN)
    date_to: str | None = Field(default=None, pattern=ISO_DATE_PATTERN)
    # Si es True, tambien re-analiza casos que ya tienen un veredicto guardado (en vez de
    # saltarlos, que es el default) -- decision explicita de quien dispara la corrida, no un
    # comportamiento fijo del backend.
    force_reanalyze: bool = False


class LLMSettingsPublic(BaseModel):
    provider_name: str
    minimax_model: str | None
    minimax_base_url: str | None
    has_api_key: bool
    updated_at: str | None


class LLMSettingsRequest(BaseModel):
    provider_name: str = "minimax"
    # None = mantener la api key ya guardada (ver settings.save_llm_config) -- asi un admin
    # puede ajustar modelo/base_url sin tener que reingresar el secreto cada vez.
    minimax_api_key: str | None = None
    minimax_model: str
    minimax_base_url: str


def _to_public(llm_config: llm_settings.LLMConfig) -> LLMSettingsPublic:
    return LLMSettingsPublic(
        provider_name=llm_config.provider_name,
        minimax_model=llm_config.minimax_model,
        minimax_base_url=llm_config.minimax_base_url,
        has_api_key=bool(llm_config.minimax_api_key),
        updated_at=llm_config.updated_at,
    )


@router.get("/settings")
def get_llm_settings(_admin: CurrentUser = Depends(require_admin)) -> LLMSettingsPublic:
    """Admin-only, igual que /auth/users -- y nunca devuelve minimax_api_key en claro (solo
    has_api_key), mismo criterio que nunca se expone password_hash via UserPublic."""
    conn = llm_settings.get_connection()
    try:
        current = llm_settings.load_llm_config(conn)
    finally:
        conn.close()

    if current is None:
        return LLMSettingsPublic(
            provider_name="minimax",
            minimax_model=None,
            minimax_base_url=None,
            has_api_key=False,
            updated_at=None,
        )
    return _to_public(current)


@router.put("/settings")
def update_llm_settings(
    request: LLMSettingsRequest, _admin: CurrentUser = Depends(require_admin)
) -> LLMSettingsPublic:
    conn = llm_settings.get_connection()
    try:
        saved = llm_settings.save_llm_config(
            conn,
            request.provider_name,
            request.minimax_api_key,
            request.minimax_model,
            request.minimax_base_url,
            datetime.now(timezone.utc).isoformat(),
        )
    finally:
        conn.close()

    return _to_public(saved)


@router.post("/run", status_code=202)
def run_benchmarks(request: BenchmarkRunRequest | None = None) -> BenchmarkRunStatus:
    try:
        return state.start_benchmark_run(
            request.directions if request else None,
            date_from=request.date_from if request else None,
            date_to=request.date_to if request else None,
            force_reanalyze=request.force_reanalyze if request else False,
        )
    except state.AlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/run/status")
def run_status() -> BenchmarkRunStatus:
    return state.benchmark_run_status()


@router.get("/runs")
def list_runs(limit: int = Query(default=50, ge=1, le=200)) -> list[BenchmarkRunRecord]:
    conn = store.get_connection()
    try:
        rows = store.list_benchmark_runs(conn, limit=limit)
    finally:
        conn.close()

    return [
        BenchmarkRunRecord(
            id=row["id"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            ok=row["ok"],
            date_from=row["date_from"],
            date_to=row["date_to"],
            force_reanalyze=row["force_reanalyze"],
            requested_directions=row["directions"],
            directions=row["result_directions"],
            error=row["error"],
        )
        for row in rows
    ]


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
