import csv
from io import BytesIO
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


def parse_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def parse_path(path: Path) -> list[dict]:
    return parse_csv(path) if path.suffix.lower() == ".csv" else parse_xlsx(path)


def _parse_workbook(source: Path | BytesIO) -> list[dict]:
    workbook = openpyxl.load_workbook(source, read_only=True, data_only=True)
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


def parse_xlsx(path: Path) -> list[dict]:
    return _parse_workbook(path)


def parse_xlsx_bytes(data: bytes) -> list[dict]:
    """Como parse_xlsx(), pero para un .xlsx que todavia no toco disco -- usado por el sync de
    contactos troceado por fecha (c3/downloads.py's fetch_window_bytes), que fetchea cada ventana
    en memoria y solo escribe UN archivo mergeado al final (ver downloads.write_merged_xlsx)."""
    return _parse_workbook(BytesIO(data))


def parse_report(name: str) -> list[dict] | None:
    path = downloads.latest_file(name)
    if path is None:
        return None
    return parse_path(path)


def parse_report_history(
    name: str, date_from: str | None = None, date_to: str | None = None
) -> list[dict] | None:
    if name in _STORE_BACKED_REPORTS:
        conn = store.get_connection()
        try:
            return store.history_rows(conn, name, date_from, date_to)
        finally:
            conn.close()

    paths = downloads.all_files(name)
    if not paths:
        return None
    records = []
    for path in paths:
        records.extend(parse_path(path))
    return records
