from pathlib import Path

import openpyxl

from ..c3 import downloads


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
    return parse_xlsx(path)
