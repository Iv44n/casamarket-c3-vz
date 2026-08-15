import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

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


@dataclass(frozen=True)
class DownloadResult:
    job: DownloadJob
    status_code: int
    path: Path
    content_type: str | None
    size_bytes: int
    elapsed_seconds: float


def attention_base_params(type_param_value: str) -> dict:
    today = config.hoy().isoformat()
    return {
        "date_init": f"{today} 00:00",
        "date_end": f"{today} 23:59",
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


def _attention_job(name: str) -> DownloadJob:
    mechanism = reports.EXPORT_MECHANISMS[name]
    params = attention_base_params(mechanism.type_param_value)
    params["with_form"] = 1
    return DownloadJob(name=name, endpoint=mechanism.export_endpoint, params=params)


def _call_job(name: str) -> DownloadJob:
    mechanism = reports.CALL_EXPORT_MECHANISMS[name]
    today = config.hoy().isoformat()
    params = {
        "date_init": f"{today} 00:00",
        "date_end": f"{today} 23:59",
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
    return DownloadJob(name=name, endpoint=reports.CALLS_EXPORT_ENDPOINT, params=params)


def _contacts_job() -> DownloadJob:
    return DownloadJob(
        name="contacts",
        endpoint=reports.CONTACTS_EXPORT_ENDPOINT,
        params=dict(reports.CONTACTS_EXPORT_DEFAULT_PARAMS),
    )


def build_jobs() -> list[DownloadJob]:
    jobs = [_attention_job(name) for name in reports.EXPORT_MECHANISMS]
    jobs += [_call_job(name) for name in reports.CALL_EXPORT_MECHANISMS]
    jobs.append(_contacts_job())
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


def _filename_from_response(response: httpx.Response, fallback: str) -> str:
    disposition = response.headers.get("content-disposition", "")
    match = re.search(r'filename="?([^";]+)"?', disposition)
    if match:
        return match.group(1)

    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    ext = _CONTENT_TYPE_EXTENSIONS.get(content_type, "")
    return f"{fallback}{ext}"


def run_job(client: httpx.Client, job: DownloadJob) -> DownloadResult:
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

    today = config.hoy().isoformat()
    filename = _filename_from_response(response, fallback="export")

    config.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    dest = config.DOWNLOADS_DIR / f"{job.name}_{today}_{filename}"
    dest.write_bytes(response.content)

    return DownloadResult(
        job=job,
        status_code=response.status_code,
        path=dest,
        content_type=content_type or None,
        size_bytes=len(response.content),
        elapsed_seconds=elapsed,
    )
