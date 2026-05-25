"""Export writers: CSV, JSON, and (optional) XLSX."""
from __future__ import annotations

import csv
import json
from typing import List

from .models import EXPORT_COLUMNS, Member


def write_csv(members: List[Member], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for m in members:
            writer.writerow(m.to_row())


def write_json(members: List[Member], path: str) -> None:
    rows = [m.to_row() for m in members]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def write_xlsx(members: List[Member], path: str) -> None:
    try:
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "xlsx export needs openpyxl. Install it: pip install openpyxl"
        ) from exc
    wb = Workbook()
    ws = wb.active
    ws.title = "members"
    ws.append(EXPORT_COLUMNS)
    for m in members:
        row = m.to_row()
        ws.append([row.get(c, "") for c in EXPORT_COLUMNS])
    wb.save(path)


def write(members: List[Member], path: str, fmt: str) -> None:
    fmt = fmt.lower()
    if fmt == "csv":
        write_csv(members, path)
    elif fmt == "json":
        write_json(members, path)
    elif fmt in ("xlsx", "excel"):
        write_xlsx(members, path)
    else:
        raise ValueError(f"unknown export format: {fmt}")
