import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import config
from ..schemas import DownloadedFile
from .data import KNOWN_REPORTS

router = APIRouter(prefix="/extraction/files", tags=["extraction"])

# `(?:_masivo)?` matches c3/massive.py's `_download` job names (e.g.
# "attention_masivo") so the reporte masivo's zip shows up alongside the
# regular daily downloads instead of being invisible in this listing.
# `[^/]+` (not `.+`) keeps a path-traversal filename from ever reconstructing
# to somewhere outside DOWNLOADS_DIR in delete_file below.
_FILENAME_RE = re.compile(
    r"^(?P<name>"
    + "|".join(sorted(KNOWN_REPORTS))
    + r")(?:_masivo)?_(?P<date>\d{4}-\d{2}-\d{2})_[^/]+$"
)


def _list_downloaded_files() -> list[DownloadedFile]:
    if not config.DOWNLOADS_DIR.exists():
        return []
    entries = []
    for path in config.DOWNLOADS_DIR.iterdir():
        if not path.is_file():
            continue
        match = _FILENAME_RE.match(path.name)
        if not match:
            continue
        entries.append(
            DownloadedFile(
                report_name=match.group("name"),
                date=match.group("date"),
                filename=path.name,
                size_bytes=path.stat().st_size,
            )
        )
    return sorted(entries, key=lambda e: (e.report_name, e.date))


@router.get("")
def list_files() -> list[DownloadedFile]:
    return _list_downloaded_files()


@router.get("/{filename}")
def download_file(filename: str) -> FileResponse:
    if not _FILENAME_RE.match(filename):
        raise HTTPException(
            status_code=400, detail=f"Nombre de archivo invalido: {filename!r}"
        )

    path = config.DOWNLOADS_DIR / filename
    if not path.is_file():
        raise HTTPException(
            status_code=404, detail=f"Archivo no encontrado: {filename!r}"
        )
    return FileResponse(path, filename=filename)


@router.delete("/{filename}")
def delete_file(filename: str) -> None:
    if not _FILENAME_RE.match(filename):
        raise HTTPException(
            status_code=400, detail=f"Nombre de archivo invalido: {filename!r}"
        )

    path = config.DOWNLOADS_DIR / filename
    if not path.is_file():
        raise HTTPException(
            status_code=404, detail=f"Archivo no encontrado: {filename!r}"
        )
    path.unlink()
