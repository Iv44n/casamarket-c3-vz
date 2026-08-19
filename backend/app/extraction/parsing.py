import csv
import threading
from pathlib import Path

import openpyxl

from ..c3 import downloads
from . import store

_STORE_BACKED_REPORTS = {
    "attention",
    "outboundattention",
    "callincoming",
    "calloutgoing",
    "transfer",
}

# Cache en memoria de lecturas de historial, por (reporte, date_from, date_to). Absorbe las
# lecturas repetidas del auto-refresh del frontend (misma fecha, cada pocos minutos, por cada
# pestaña abierta) sin importar si el filtrado en SQL ya bajo el costo de cada lectura --
# el auto-refresh igual dispara `router.invalidate()` sin importar si algo cambio.
_history_cache: dict[tuple[str, str | None, str | None], list[dict] | None] = {}
_history_cache_lock = threading.Lock()


def invalidate_history_cache(report_name: str) -> None:
    """Descarta todas las entradas cacheadas de un reporte tras una escritura exitosa -- la
    proxima lectura de cualquier rango de ese reporte vuelve a pegarle a la DB. Se invalida el
    reporte completo, no solo el rango tocado por la escritura: mas simple y seguro, y las
    escrituras (cada 5 minutos como minimo) son mucho menos frecuentes que las lecturas."""
    with _history_cache_lock:
        for key in [k for k in _history_cache if k[0] == report_name]:
            del _history_cache[key]


def parse_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def parse_path(path: Path) -> list[dict]:
    return parse_csv(path) if path.suffix.lower() == ".csv" else parse_xlsx(path)


def parse_xlsx(path: Path) -> list[dict]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        records = []
        for sheet in workbook.worksheets:
            rows = sheet.iter_rows(values_only=True)
            header = next(rows, None)
            if header is None or all(cell is None for cell in header):
                continue
            columns = [str(cell) if cell is not None else "" for cell in header]
            for row in rows:
                if all(cell is None for cell in row):
                    continue
                records.append(dict(zip(columns, row)))
        return records
    finally:
        workbook.close()


def parse_report(name: str) -> list[dict] | None:
    path = downloads.latest_file(name)
    if path is None:
        return None
    return parse_path(path)


def parse_report_history(
    name: str, date_from: str | None = None, date_to: str | None = None
) -> list[dict] | None:
    if name in _STORE_BACKED_REPORTS:
        cache_key = (name, date_from, date_to)
        with _history_cache_lock:
            if cache_key in _history_cache:
                return _history_cache[cache_key]
        conn = store.get_connection()
        try:
            rows = store.history_rows(conn, name, date_from, date_to)
        finally:
            conn.close()
        with _history_cache_lock:
            _history_cache[cache_key] = rows
        return rows

    paths = downloads.all_files(name)
    if not paths:
        return None
    records = []
    for path in paths:
        records.extend(parse_path(path))
    return records
