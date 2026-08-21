"""Vehicle-fitment ("This fits...") data.

The table is never present in the raw product-page HTML - it's populated
client-side via a JSONP call to a third-party fitment app the store uses
(capacitywebservices.com). One call per *product* (keyed by the Shopify
product id) returns every compatible vehicle for every variant of that
product, each row tagged with the SKU it applies to.

Column semantics, per user decision:
- `auto`: only Year||Make||Model combos (year ranges expanded to individual
  years), deduplicated/sorted, wrapped as `{combo1,combo2,...}`.
- Submodel / Engine / Body Type / Bed Length: NOT part of `auto`. Instead,
  grouped by Make: unique values per make, "N/A" dropped, formatted as
  `Make1: {v1, v2}, Make2: {v3}`. A column is left empty if every value for
  that field is "N/A" across the whole table.
"""
from __future__ import annotations

import html as html_module
import json
import logging
import re
from dataclasses import dataclass

from selectolax.parser import HTMLParser

from core.http_client import Client

log = logging.getLogger(__name__)

_YMM_URL = "https://www.ymmshopify.capacitywebservices.com/ajax/get_dropdowns_version3.php"
_SHOP_DOMAIN = "awe-tuning.myshopify.com"

_DISPLAY_HEADERS = ["Make", "Model", "Year", "Submodel", "Engine", "Body Type", "Bed Length"]


@dataclass
class FitmentRow:
    make: str
    model: str
    year: str
    submodel: str
    engine: str
    body_type: str
    bed_length: str
    sku: str


@dataclass
class VariantFitment:
    auto: str | None = None
    submodel: str | None = None
    engine: str | None = None
    body_type: str | None = None
    bed_length: str | None = None
    html: str | None = None


def _strip_jsonp(text: str) -> dict | None:
    match = re.search(r"\((\{.*\})\)\s*;?\s*$", text, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _clean_header(text: str) -> str:
    return re.sub(r"[^\w\s/]+$", "", text).strip()


def _parse_table(html_fragment: str) -> list[FitmentRow]:
    table = HTMLParser(html_fragment).css_first("table.ymm_table")
    if table is None:
        return []
    headers = [_clean_header(th.text(strip=True)) for th in table.css("thead th")]
    rows = []
    for tr in table.css("tbody tr"):
        cells = [td.text(strip=True) for td in tr.css("td")]
        if len(cells) != len(headers):
            continue
        by_header = dict(zip(headers, cells))
        rows.append(
            FitmentRow(
                make=by_header.get("Make", ""),
                model=by_header.get("Model", ""),
                year=by_header.get("Year", ""),
                submodel=by_header.get("Submodel", ""),
                engine=by_header.get("Engine", ""),
                body_type=by_header.get("Body Type", ""),
                bed_length=by_header.get("Bed Length", ""),
                sku=by_header.get("SKU", ""),
            )
        )
    return rows


async def fetch_compatibility_table(client: Client, product_id: int) -> list[FitmentRow]:
    params = {
        "callback": "ymmCb",
        "domain": _SHOP_DOMAIN,
        "load": "all",
        "version": "updated",
        "action": "get_compatible",
        "current_productid": product_id,
        "current_ymmpage": 1,
        "ymm_limit": 20000,
        "lang_code": "en",
        "pri_lang_code": "en",
    }
    try:
        text = await client.get_text(_YMM_URL, params=params)
    except Exception:
        log.warning("fitment lookup failed for product %s", product_id, exc_info=True)
        return []

    payload = _strip_jsonp(text)
    if not payload or not payload.get("html"):
        return []
    return _parse_table(payload["html"])


def _expand_years(year_str: str) -> list[str]:
    year_str = year_str.strip()
    m = re.match(r"^(\d{4})\s*-\s*(\d{4})$", year_str)
    if m:
        start, end = int(m.group(1)), int(m.group(2))
        return [str(y) for y in range(start, end + 1)]
    if re.match(r"^\d{4}$", year_str):
        return [year_str]
    return [year_str] if year_str else []


def _format_auto(rows: list[FitmentRow]) -> str | None:
    combos = {
        f"{year}||{row.make}||{row.model}"
        for row in rows
        for year in _expand_years(row.year)
    }
    return "{" + ",".join(sorted(combos)) + "}" if combos else None


def _format_grouped(rows: list[FitmentRow], value_of) -> str | None:
    by_make: dict[str, set[str]] = {}
    for row in rows:
        value = value_of(row).strip()
        if not value or value.upper() == "N/A":
            continue
        by_make.setdefault(row.make, set()).add(value)
    if not by_make:
        return None
    parts = (f"{make}: {{{', '.join(sorted(values))}}}" for make, values in sorted(by_make.items()))
    return ", ".join(parts)


def _build_html_table(rows: list[FitmentRow]) -> str | None:
    if not rows:
        return None
    head = "".join(f"<th>{h}</th>" for h in _DISPLAY_HEADERS)
    body = "".join(
        "<tr>"
        + "".join(
            f"<td>{html_module.escape(v)}</td>"
            for v in (r.make, r.model, r.year, r.submodel, r.engine, r.body_type, r.bed_length)
        )
        + "</tr>"
        for r in rows
    )
    return f'<table class="variant-fits__content"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def build_variant_fitment(rows: list[FitmentRow], sku: str) -> VariantFitment:
    variant_rows = [r for r in rows if r.sku == sku]
    if not variant_rows:
        return VariantFitment()
    return VariantFitment(
        auto=_format_auto(variant_rows),
        submodel=_format_grouped(variant_rows, lambda r: r.submodel),
        engine=_format_grouped(variant_rows, lambda r: r.engine),
        body_type=_format_grouped(variant_rows, lambda r: r.body_type),
        bed_length=_format_grouped(variant_rows, lambda r: r.bed_length),
        html=_build_html_table(variant_rows),
    )
