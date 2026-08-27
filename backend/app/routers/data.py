from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth.dependencies import get_current_user
from ..extraction import parsing, store
from ..schemas import DailyCount

router = APIRouter(prefix="/data", tags=["data"], dependencies=[Depends(get_current_user)])

ISO_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"

KNOWN_REPORTS = {
    "attention",
    "outboundattention",
    "callincoming",
    "calloutgoing",
    "contacts",
    "transfer",
}

# Los unicos reportes con una columna de fecha mapeada para agregar por dia (ver
# store._HISTORY_DATE_COLUMN) -- "contacts" no tiene rango de fechas y "transfer" se
# correlaciona por id_atencion, no por dia (mismo motivo que ambos quedan afuera del filtro de
# fecha en history_rows).
DAILY_COUNT_REPORTS = {"attention", "outboundattention", "callincoming", "calloutgoing"}

DIRECTION_VALUES = {"all", "incoming", "outgoing"}

@router.get("/attention-records")
def get_attention_records(
    direction: str = Query(default="all"),
    estados: list[str] | None = Query(default=None),
    campana: str | None = Query(default=None),
    agentes: list[str] | None = Query(default=None),
    date_from: str | None = Query(default=None, pattern=ISO_DATE_PATTERN),
    date_to: str | None = Query(default=None, pattern=ISO_DATE_PATTERN),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict:
    if direction not in DIRECTION_VALUES:
        raise HTTPException(
            status_code=422,
            detail=f"direction invalido: {direction!r}. Validos: {sorted(DIRECTION_VALUES)}",
        )

    conn = store.get_connection()
    try:
        page_result = store.attention_records_page(
            conn,
            direction=direction,
            estados=estados,
            campana=campana,
            agentes=agentes,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
    finally:
        conn.close()

    return {
        "total": page_result.total,
        "staleCount": page_result.stale_count,
        "rows": page_result.rows,
        "transfers": page_result.transfers,
    }


@router.get("/{report_name}")
def get_report(report_name: str) -> list[dict]:
    if report_name not in KNOWN_REPORTS:
        raise HTTPException(
            status_code=404,
            detail=f"Reporte desconocido: {report_name!r}. Validos: {sorted(KNOWN_REPORTS)}",
        )

    records = parsing.parse_report(report_name)
    if records is None:
        raise HTTPException(
            status_code=404,
            detail=f"Todavia no se descargo ningun archivo de '{report_name}'.",
        )
    return records


@router.get("/{report_name}/page")
def get_report_page(
    report_name: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict:
    """Devuelve una pagina del reporte (slice server-side) + el total de filas,
    para que el frontend no necesite cargar y transferir el archivo completo en
    cada cambio de pagina -- el endpoint /{report_name} sin paginar sigue
    disponible para los callers que necesitan todas las filas de una (contacts
    index, summary)."""
    if report_name not in KNOWN_REPORTS:
        raise HTTPException(
            status_code=404,
            detail=f"Reporte desconocido: {report_name!r}. Validos: {sorted(KNOWN_REPORTS)}",
        )

    records = parsing.parse_report(report_name)
    if records is None:
        raise HTTPException(
            status_code=404,
            detail=f"Todavia no se descargo ningun archivo de '{report_name}'.",
        )
    total = len(records)
    start = (page - 1) * page_size
    page_rows = records[start : start + page_size]
    return {"total": total, "rows": page_rows}


@router.get("/{report_name}/history")
def get_report_history(
    report_name: str,
    date_from: str | None = Query(default=None, pattern=ISO_DATE_PATTERN),
    date_to: str | None = Query(default=None, pattern=ISO_DATE_PATTERN),
) -> list[dict]:
    if report_name not in KNOWN_REPORTS:
        raise HTTPException(
            status_code=404,
            detail=f"Reporte desconocido: {report_name!r}. Validos: {sorted(KNOWN_REPORTS)}",
        )

    records = parsing.parse_report_history(report_name, date_from, date_to)
    if records is None:
        raise HTTPException(
            status_code=404,
            detail=f"Todavia no se descargo ningun archivo de '{report_name}'.",
        )
    return records


@router.get("/{report_name}/history/daily-counts")
def get_report_daily_counts(
    report_name: str,
    date_from: str | None = Query(default=None, pattern=ISO_DATE_PATTERN),
    date_to: str | None = Query(default=None, pattern=ISO_DATE_PATTERN),
    agentes: list[str] | None = Query(default=None),
) -> list[DailyCount]:
    """Conteo de filas por dia (GROUP BY server-side) para graficos de tendencia -- ver
    store.daily_counts() para por que existe: no requiere traer/parsear cada row_json como
    /{report_name}/history, asi que es sensiblemente mas liviano para rangos largos.
    `agentes` (mismo patron repetido que /attention-records) filtra antes del GROUP BY, para
    poder excluir agentes especiales sin perder el camino rapido."""
    if report_name not in DAILY_COUNT_REPORTS:
        raise HTTPException(
            status_code=404,
            detail=f"Reporte desconocido: {report_name!r}. Validos: {sorted(DAILY_COUNT_REPORTS)}",
        )

    conn = store.get_connection()
    try:
        return store.daily_counts(conn, report_name, date_from, date_to, agentes=agentes)
    finally:
        conn.close()
