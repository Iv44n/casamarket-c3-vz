from fastapi import APIRouter, HTTPException, Query

from ..extraction import parsing, store

router = APIRouter(prefix="/data", tags=["data"])

ISO_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"

KNOWN_REPORTS = {
    "attention",
    "outboundattention",
    "callincoming",
    "calloutgoing",
    "contacts",
    "transfer",
}

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
