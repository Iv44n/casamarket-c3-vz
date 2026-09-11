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
    model: str | None
    base_url: str | None
    has_api_key: bool
    updated_at: str | None


class LLMSettingsRequest(BaseModel):
    provider_name: llm_settings.LLMProviderName = "minimax"
    # None = mantener la api key ya guardada (ver settings.save_llm_config) -- asi un admin
    # puede ajustar proveedor/modelo/base_url sin tener que reingresar el secreto cada vez.
    api_key: str | None = None
    model: str
    # None = usar el default fijo del proveedor elegido (ver llm/__init__.py's
    # _OPENAI_COMPATIBLE_DEFAULTS) -- solo hace falta llenarlo para pisarlo (ej. apuntar
    # "minimax" a OpenRouter) o si el proveedor es "claude" (que lo ignora del todo).
    base_url: str | None = None


def _to_public(llm_config: llm_settings.LLMConfig) -> LLMSettingsPublic:
    return LLMSettingsPublic(
        provider_name=llm_config.provider_name,
        model=llm_config.model,
        base_url=llm_config.base_url,
        has_api_key=bool(llm_config.api_key),
        updated_at=llm_config.updated_at,
    )


@router.get("/settings")
def get_llm_settings(_admin: CurrentUser = Depends(require_admin)) -> LLMSettingsPublic:
    """Admin-only, igual que /auth/users -- y nunca devuelve api_key en claro (solo
    has_api_key), mismo criterio que nunca se expone password_hash via UserPublic."""
    conn = llm_settings.get_connection()
    try:
        current = llm_settings.load_llm_config(conn)
    finally:
        conn.close()

    if current is None:
        return LLMSettingsPublic(
            provider_name="minimax",
            model=None,
            base_url=None,
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
            request.api_key,
            request.model,
            request.base_url,
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
    """Trae TODO el rango de una -- lo consumen las agregaciones por agente del frontend
    (KPIs, ranking, grafico de productividad), que necesitan el dataset completo. Para listar
    casos individuales de a una pagina usar GET /results/page."""
    conn = store.get_connection()
    try:
        rows = store.benchmark_result_rows(
            conn, direction=direction, date_from=date_from, date_to=date_to
        )
    finally:
        conn.close()
    return rows


@router.get("/results/page")
def results_page(
    direction: Literal["attention", "outboundattention"] | None = Query(default=None),
    date_from: str | None = Query(default=None, pattern=ISO_DATE_PATTERN),
    date_to: str | None = Query(default=None, pattern=ISO_DATE_PATTERN),
    agentes: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict:
    """Version paginada (LIMIT/OFFSET server-side, ver store.benchmark_results_page) para la
    tabla de casos de /benchmarks -- mismo shape de respuesta que GET /data/attention-records."""
    conn = store.get_connection()
    try:
        page_result = store.benchmark_results_page(
            conn,
            direction=direction,
            date_from=date_from,
            date_to=date_to,
            agentes=agentes,
            page=page,
            page_size=page_size,
        )
    finally:
        conn.close()
    return {"total": page_result.total, "rows": page_result.rows}
