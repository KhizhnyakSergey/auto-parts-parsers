"""Persist scraped product-variant rows to JSON Lines (raw/complete) and Excel.

Excel columns split into two groups:
- fixed: always present, one getter per column.
- dynamic: on-site tab names (e.g. "Performance Specs") and "Instruction N"
  columns, whose *set* isn't known until we've seen every row - Shopify tabs
  differ per product, so these are computed from the actual data each run.
"""
from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .models import ProductRow

_EXCEL_CELL_LIMIT = 32000

_FIXED_COLUMNS_HEAD = [
    ("product_id", lambda r: r.product_id),
    ("variant_id", lambda r: r.variant_id),
    ("sku", lambda r: r.sku),
    ("title", lambda r: r.title),
    ("url", lambda r: r.url),
    ("vendor", lambda r: r.vendor),
    ("product_type", lambda r: r.product_type),
    ("categories", lambda r: ", ".join(r.categories)),
    ("vehicle_brands", lambda r: ", ".join(r.vehicle_brands)),
    ("tags", lambda r: ", ".join(r.tags)),
    ("price", lambda r: r.price),
    ("compare_at_price", lambda r: r.compare_at_price),
    ("currency", lambda r: r.currency),
    ("in_stock", lambda r: r.in_stock),
]

_FIXED_COLUMNS_TAIL = [
    ("description", lambda r: r.description),
    ("details_text", lambda r: r.details_text),
    ("important_fitment_notes", lambda r: r.important_fitment_notes),
]

_FITMENT_COLUMNS = [
    ("auto", lambda r: r.auto),
    ("Submodel", lambda r: r.submodel),
    ("Engine", lambda r: r.engine),
    ("Body Type", lambda r: r.body_type),
    ("Bed Length", lambda r: r.bed_length),
    ("variant_fits_html", lambda r: r.variant_fits_html),
]

_TRAILING_COLUMNS = [
    ("created_at", lambda r: r.created_at),
    ("updated_at", lambda r: r.updated_at),
]

_WIDTHS = {
    "title": 45,
    "url": 40,
    "categories": 25,
    "vehicle_brands": 20,
    "tags": 30,
    "description": 60,
    "details_text": 60,
    "important_fitment_notes": 40,
    "auto": 50,
    "variant_fits_html": 50,
}


def _excel_safe(value):
    if isinstance(value, str) and len(value) > _EXCEL_CELL_LIMIT:
        return value[:_EXCEL_CELL_LIMIT] + " …[truncated]"
    return value


def _tab_columns(rows: list[ProductRow]) -> list[str]:
    names: set[str] = set()
    for row in rows:
        names.update(row.tabs.keys())
    return sorted(names)


def _instruction_columns(rows: list[ProductRow]) -> list[str]:
    max_links = max((len(row.instruction_links) for row in rows), default=0)
    return [f"Instruction {i + 1}" for i in range(max_links)]


def _video_columns(rows: list[ProductRow]) -> list[str]:
    max_videos = max((len(row.video_links) for row in rows), default=0)
    return [f"Video {i + 1}" for i in range(max_videos)]


def _image_columns(rows: list[ProductRow]) -> list[str]:
    max_images = max((len(row.images) for row in rows), default=0)
    return [f"Image {i + 1}" for i in range(max_images)]


def _build_columns(rows: list[ProductRow]):
    image_names = _image_columns(rows)
    tab_names = _tab_columns(rows)
    instruction_names = _instruction_columns(rows)
    video_names = _video_columns(rows)

    image_columns = [
        (name, (lambda r, i=i: r.images[i] if i < len(r.images) else ""))
        for i, name in enumerate(image_names)
    ]
    tab_columns = [(name, (lambda r, n=name: r.tabs.get(n, ""))) for name in tab_names]
    instruction_columns = [
        (name, (lambda r, i=i: r.instruction_links[i] if i < len(r.instruction_links) else ""))
        for i, name in enumerate(instruction_names)
    ]
    video_columns = [
        (name, (lambda r, i=i: r.video_links[i] if i < len(r.video_links) else ""))
        for i, name in enumerate(video_names)
    ]
    return (
        _FIXED_COLUMNS_HEAD
        + image_columns
        + _FIXED_COLUMNS_TAIL
        + tab_columns
        + instruction_columns
        + video_columns
        + _FITMENT_COLUMNS
        + _TRAILING_COLUMNS
    )


def write_jsonl(rows: list[ProductRow], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(row.model_dump_json() + "\n")


def write_xlsx(rows: list[ProductRow], path: Path) -> None:
    columns = _build_columns(rows)

    wb = Workbook()
    ws: Worksheet = wb.active
    ws.title = "Products"

    ws.append([name for name, _ in columns])
    for cell in ws[1]:
        cell.font = cell.font.copy(bold=True)

    for row in rows:
        ws.append([_excel_safe(getter(row)) for _, getter in columns])

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{len(rows) + 1}"
    for idx, (name, _) in enumerate(columns, start=1):
        default_width = 40 if name.startswith("Image ") else 16
        ws.column_dimensions[get_column_letter(idx)].width = _WIDTHS.get(name, default_width)

    wb.save(path)


def load_jsonl(path: Path) -> list[ProductRow]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [ProductRow.model_validate(json.loads(line)) for line in f if line.strip()]
