import re
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import httpx
import openpyxl

from .. import config
from . import reports

_CONTENT_TYPE_EXTENSIONS = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "text/csv": ".csv",
    "application/pdf": ".pdf",
    "application/zip": ".zip",
}


class DownloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class DownloadJob:
    name: str
    endpoint: str
    params: dict = field(default_factory=dict)
    file_date: date = field(default_factory=config.hoy)
    file_label: str | None = None


@dataclass(frozen=True)
class DownloadResult:
    job: DownloadJob
    status_code: int
    path: Path | None
    content_type: str | None
    size_bytes: int
    elapsed_seconds: float


def _attention_params(type_param_value: str, date_init: str, date_end: str) -> dict:
    return {
        "date_init": date_init,
        "date_end": date_end,
        "agent": "",
        "campaign": "",
        "attention_id": "",
        "number": "",
        "whatsapp_number_id": "",
        "status": "",
        "type": type_param_value,
        "condition": "",
        "message": "",
        "vip_only": "false",
        "labels": "",
    }


def attention_base_params(type_param_value: str, target_date: date | None = None) -> dict:
    day = (target_date or config.hoy()).isoformat()
    return _attention_params(type_param_value, f"{day} 00:00", f"{day} 23:59")


def attention_range_params(type_param_value: str, date_from: str, date_to: str) -> dict:
    """Como attention_base_params, pero para un RANGO real (date_init distinto de date_end,
    ambos ISO 'YYYY-MM-DD') -- usado por c3/massive.py para pedir el reporte masivo scopeado
    al rango real de una corrida de benchmarks, en vez de siempre "hoy" (ver ese modulo, y el
    porque: confirmado en vivo el 2026-09-03 que el reporte masivo ignoraba el rango pedido y
    siempre devolvia el zip de hoy, porque _trigger() nunca le pasaba una fecha a
    attention_base_params -- quedaba en su default de config.hoy())."""
    return _attention_params(type_param_value, f"{date_from} 00:00", f"{date_to} 23:59")


def _attention_job(name: str, target_date: date | None = None) -> DownloadJob:
    mechanism = reports.EXPORT_MECHANISMS[name]
    params = attention_base_params(mechanism.type_param_value, target_date)
    params["with_form"] = 1
    return DownloadJob(
        name=name,
        endpoint=mechanism.export_endpoint,
        params=params,
        file_date=target_date or config.hoy(),
    )


def _call_job(name: str, target_date: date | None = None) -> DownloadJob:
    mechanism = reports.CALL_EXPORT_MECHANISMS[name]
    day = (target_date or config.hoy()).isoformat()
    params = {
        "date_init": f"{day} 00:00",
        "date_end": f"{day} 23:59",
        "agent": "",
        "campaign": "",
        "linkedid": "",
        "number": "",
        "disposition": "",
        "typeExport": mechanism.type_export_value,
        "labels": "",
        "from_whatsapp": "",
        "with": mechanism.selected_with,
        **mechanism.extra_params,
    }
    return DownloadJob(
        name=name,
        endpoint=reports.CALLS_EXPORT_ENDPOINT,
        params=params,
        file_date=target_date or config.hoy(),
    )


def _contacts_sync_jobs(today: date) -> list[DownloadJob]:
    """Un DownloadJob por ventana de config.CONTACTS_SYNC_WINDOW_DAYS dias, cubriendo
    [today - CONTACTS_SYNC_LOOKBACK_DAYS, today] sin huecos ni superposicion -- ver
    reports.contacts_export_window_params sobre por que particionar por created_at es seguro.
    Estos jobs nunca se escriben a disco individualmente (ver downloads.fetch_window_bytes /
    extraction/service.py's run_contacts_sync_jobs) -- file_label solo identifica la ventana en
    logs/JobSummary.name, no un archivo real."""
    window = timedelta(days=config.CONTACTS_SYNC_WINDOW_DAYS)
    range_start = today - timedelta(days=config.CONTACTS_SYNC_LOOKBACK_DAYS)

    jobs = []
    window_start = range_start
    while window_start <= today:
        window_end = min(window_start + window - timedelta(days=1), today)
        jobs.append(
            DownloadJob(
                name="contacts",
                endpoint=reports.CONTACTS_EXPORT_ENDPOINT,
                params=reports.contacts_export_window_params(
                    window_start.isoformat(), window_end.isoformat()
                ),
                file_date=today,
                file_label=f"chunk_{window_start.isoformat()}_to_{window_end.isoformat()}",
            )
        )
        window_start = window_end + timedelta(days=1)
    return jobs


def _transfer_job(target_date: date | None = None) -> DownloadJob:
    day = (target_date or config.hoy()).isoformat()
    params = {
        "date_init": f"{day} 00:00",
        "date_end": f"{day} 23:59",
        **reports.TRANSFER_EXPORT_DEFAULT_PARAMS,
    }
    return DownloadJob(
        name="transfer",
        endpoint=reports.TRANSFER_EXPORT_ENDPOINT,
        params=params,
        file_date=target_date or config.hoy(),
    )


def build_jobs() -> list[DownloadJob]:
    jobs = [_attention_job(name) for name in reports.EXPORT_MECHANISMS]
    jobs += [_call_job(name) for name in reports.CALL_EXPORT_MECHANISMS]
    jobs.append(_transfer_job())
    return jobs


def build_contacts_sync_jobs(today: date | None = None) -> list[DownloadJob]:
    return _contacts_sync_jobs(today or config.hoy())


def build_backfill_jobs(target_date: date) -> list[DownloadJob]:
    jobs = [_attention_job(name, target_date) for name in reports.EXPORT_MECHANISMS]
    jobs += [_call_job(name, target_date) for name in reports.CALL_EXPORT_MECHANISMS]
    jobs.append(_transfer_job(target_date))
    return jobs


def _historical_label(date_init: date, date_end: date) -> str:
    return f"historical_{date_init.isoformat()}_to_{date_end.isoformat()}"


def _attention_job_historical(name: str, date_init: date, date_end: date) -> DownloadJob:
    mechanism = reports.EXPORT_MECHANISMS[name]
    params = {
        "date_init": f"{date_init.isoformat()} 00:00",
        "date_end": f"{date_end.isoformat()} 23:59",
        "agent": "",
        "campaign": "",
        "attention_id": "",
        "number": "",
        "whatsapp_number_id": "",
        "status": "",
        "type": mechanism.type_param_value,
        "condition": "",
        "message": "",
        "vip_only": "false",
        "labels": "",
        "with_form": 1,
    }
    return DownloadJob(
        name=name,
        endpoint=mechanism.export_endpoint,
        params=params,
        file_date=date_end,
        file_label=_historical_label(date_init, date_end),
    )


def _call_job_historical(name: str, date_init: date, date_end: date) -> DownloadJob:
    mechanism = reports.CALL_EXPORT_MECHANISMS[name]
    params = {
        "date_init": f"{date_init.isoformat()} 00:00",
        "date_end": f"{date_end.isoformat()} 23:59",
        "agent": "",
        "campaign": "",
        "linkedid": "",
        "number": "",
        "disposition": "",
        "typeExport": mechanism.type_export_value,
        "labels": "",
        "from_whatsapp": "",
        "with": mechanism.selected_with,
        **mechanism.extra_params,
    }
    return DownloadJob(
        name=name,
        endpoint=reports.CALLS_EXPORT_ENDPOINT,
        params=params,
        file_date=date_end,
        file_label=_historical_label(date_init, date_end),
    )


def _transfer_job_historical(date_init: date, date_end: date) -> DownloadJob:
    params = {
        "date_init": f"{date_init.isoformat()} 00:00",
        "date_end": f"{date_end.isoformat()} 23:59",
        **reports.TRANSFER_EXPORT_DEFAULT_PARAMS,
    }
    return DownloadJob(
        name="transfer",
        endpoint=reports.TRANSFER_EXPORT_ENDPOINT,
        params=params,
        file_date=date_end,
        file_label=_historical_label(date_init, date_end),
    )


def build_historical_jobs(date_init: date, date_end: date) -> list[DownloadJob]:
    jobs = [
        _attention_job_historical(name, date_init, date_end)
        for name in reports.EXPORT_MECHANISMS
    ]
    jobs += [
        _call_job_historical(name, date_init, date_end)
        for name in reports.CALL_EXPORT_MECHANISMS
    ]
    jobs.append(_transfer_job_historical(date_init, date_end))
    return jobs


def latest_file(name: str) -> Path | None:
    if not config.DOWNLOADS_DIR.exists():
        return None
    candidates = list(config.DOWNLOADS_DIR.glob(f"{name}_20??-??-??_*"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def all_files(name: str) -> list[Path]:
    if not config.DOWNLOADS_DIR.exists():
        return []
    candidates = list(config.DOWNLOADS_DIR.glob(f"{name}_20??-??-??_*"))
    return sorted(candidates, key=lambda path: path.stat().st_mtime)


# Cuantos archivos por reporte conservar en downloads/ -- cada refresh/backfill
# escribe uno nuevo sin borrar el anterior, asi que sin esto el directorio crece
# sin limite. 7 alcanza para una semana de corridas diarias + margen para
# reintentos; latest_file() solo necesita el mas reciente y all_files() (usado
# solo por contacts, cuyo historico vive en Turso) tampoco necesita mas.
_KEEP_PER_REPORT = 7


def prune_old_files(name: str, keep: int = _KEEP_PER_REPORT) -> int:
    """Borra los archivos viejos de `name` en downloads/, conservando los `keep`
    mas recientes por mtime. Devuelve cuantos elimino. No falla si el directorio
    o los archivos no existen -- es best-effort, no bloquea la descarga."""
    if not config.DOWNLOADS_DIR.exists():
        return 0
    # glob amplio (name_*) para incluir tambien archivos historical_* que el
    # patron 20??-??-?? no atrapa, no solo los de fecha simple.
    candidates = sorted(
        config.DOWNLOADS_DIR.glob(f"{name}_*"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    removed = 0
    for stale in candidates[keep:]:
        try:
            stale.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def _filename_from_response(response: httpx.Response, fallback: str) -> str:
    disposition = response.headers.get("content-disposition", "")
    match = re.search(r'filename="?([^";]+)"?', disposition)
    if match:
        return match.group(1)

    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    ext = _CONTENT_TYPE_EXTENSIONS.get(content_type, "")
    return f"{fallback}{ext}"


def _fetch_and_validate(client: httpx.Client, job: DownloadJob) -> tuple[httpx.Response, float]:
    started = time.monotonic()
    response = client.get(job.endpoint, params=job.params or None)
    elapsed = time.monotonic() - started

    response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        raise DownloadError(
            f"'{job.name}' devolvio HTML en vez de un archivo -- probable "
            f"pagina de login o error del servidor, no el reporte esperado."
        )
    if not response.content:
        raise DownloadError(f"'{job.name}' devolvio una respuesta vacia.")

    return response, elapsed


def run_job(client: httpx.Client, job: DownloadJob) -> DownloadResult:
    response, elapsed = _fetch_and_validate(client, job)
    content_type = response.headers.get("content-type", "")

    filename = _filename_from_response(response, fallback="export")

    label = job.file_label if job.file_label is not None else job.file_date.isoformat()
    config.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    dest = config.DOWNLOADS_DIR / f"{job.name}_{label}_{filename}"
    dest.write_bytes(response.content)

    prune_old_files(job.name)

    return DownloadResult(
        job=job,
        status_code=response.status_code,
        path=dest,
        content_type=content_type or None,
        size_bytes=len(response.content),
        elapsed_seconds=elapsed,
    )


def fetch_window_bytes(client: httpx.Client, job: DownloadJob) -> tuple[bytes, int, float]:
    """Como run_job(), pero sin escribir a disco -- usado por el sync de contactos troceado por
    fecha (extraction/service.py's run_contacts_sync_jobs): un archivo por ventana en
    config.DOWNLOADS_DIR confundiria a latest_file("contacts"), que espera UN archivo = el roster
    completo. El caller mergea las filas de todas las ventanas y recien ahi escribe un unico
    archivo (ver write_merged_xlsx)."""
    response, elapsed = _fetch_and_validate(client, job)
    return response.content, response.status_code, elapsed


def write_merged_xlsx(rows: list[dict], file_date: date) -> Path:
    """Arma un .xlsx de una sola hoja a partir de filas ya mergeadas (mismo shape que
    parsing.parse_xlsx() lee) y lo guarda como config.DOWNLOADS_DIR/contacts_<file_date>_sync.xlsx
    -- el mismo patron de nombre `contacts_20??-??-??_*` que latest_file("contacts") ya espera, asi
    que /data/contacts no necesita cambios. `rows` no puede ser vacio -- el caller decide no
    llamar aca cuando ninguna ventana trajo filas, para no pisar el ultimo archivo bueno con uno
    vacio."""
    if not rows:
        raise ValueError("write_merged_xlsx() necesita al menos una fila.")

    columns = list(rows[0].keys())
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(columns)
    for row in rows:
        sheet.append([row.get(column) for column in columns])

    config.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    dest = config.DOWNLOADS_DIR / f"contacts_{file_date.isoformat()}_sync.xlsx"
    workbook.save(dest)
    workbook.close()

    prune_old_files("contacts")
    return dest
