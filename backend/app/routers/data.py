from fastapi import APIRouter, HTTPException

from ..extraction import parsing

router = APIRouter(prefix="/data", tags=["data"])

KNOWN_REPORTS = {"attention", "outboundattention", "callincoming", "calloutgoing", "contacts"}


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
def get_report_history(report_name: str) -> list[dict]:
    if report_name not in KNOWN_REPORTS:
        raise HTTPException(
            status_code=404,
            detail=f"Reporte desconocido: {report_name!r}. Validos: {sorted(KNOWN_REPORTS)}",
        )

    records = parsing.parse_report_history(report_name)
    if records is None:
        raise HTTPException(
            status_code=404,
            detail=f"Todavia no se descargo ningun archivo de '{report_name}'.",
        )
    return records
