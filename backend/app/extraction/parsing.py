import csv
from pathlib import Path

import openpyxl

from ..c3 import downloads


def parse_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _parse_file(path: Path) -> list[dict]:
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
    return _parse_file(path)


def parse_report_history(name: str) -> list[dict] | None:
    paths = downloads.all_files(name)
    if not paths:
        return None
    records = []
    for path in paths:
        records.extend(_parse_file(path))
    return records
