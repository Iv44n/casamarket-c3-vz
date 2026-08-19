from fastapi import APIRouter, HTTPException, Query

from ..extraction import parsing

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
