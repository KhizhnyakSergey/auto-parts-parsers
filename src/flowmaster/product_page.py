"""Parse one Flowmaster product page.

Most data comes from the `<script id="product_data">` JSON blob every product
page embeds (partnumber, price, stock quantity, brand, images, videos,
category hierarchy, lifecycle status - active vs. obsolete/discontinued).

A few pieces only exist in the rendered HTML, not that JSON:
- breadcrumbs, title, short description, stock-status text, on-page price
- the product photo gallery (ordered by `data-fresco-index`)
- the collapsible Overview / Specs / Emissions / Tech Resources sections

Vehicle Applications is deliberately *not* scraped here - that section's
`<div id="vehicle-applications">` is empty in the raw HTML, filled in
client-side via AJAX. See `fitment.py`.
"""
from __future__ import annotations

import json
import logging
import re

from core.http_client import Client
from selectolax.parser import HTMLParser

from .models import FlowmasterRow

log = logging.getLogger(__name__)

_PRODUCT_DATA_RE = re.compile(
    r'<script[^>]*id="product_data"[^>]*>(.*?)</script>', re.S
)


def _clean_url(url: str) -> str:
    url = url.strip()
    return "https:" + url if url.startswith("//") else url


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_product_data(html: str) -> dict:
    match = _PRODUCT_DATA_RE.search(html)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        log.warning("could not parse product_data JSON blob")
        return {}


def _extract_breadcrumbs(tree: HTMLParser) -> str:
    block = tree.css_first(".breadcrumbs")
    if block is None:
        return ""
    parts = []
    for li in block.css("li"):
        link = li.css_first("a")
        # The " / " separator is a sibling of <a>, not nested in it, so
        # a.text() naturally excludes it - only the last (current-page) crumb
        # has no <a> and no separator.
        text = link.text(strip=True) if link is not None else li.text(strip=True)
        if text:
            parts.append(text)
    return " / ".join(parts)


def _extract_title(tree: HTMLParser) -> str:
    el = tree.css_first("h1.product-name")
    return el.text(strip=True) if el is not None else ""


def _extract_short_description(tree: HTMLParser) -> str:
    el = tree.css_first(".short-description p.show-less")
    return el.text(strip=True) if el is not None else ""


def _extract_stock_status(tree: HTMLParser) -> str:
    el = tree.css_first(".product-stock-status")
    return el.text(strip=True) if el is not None else ""


def _extract_price(tree: HTMLParser) -> float | None:
    el = tree.css_first(".price .webprice")
    if el is None:
        return None
    raw = el.attributes.get("data-price")
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def _extract_sku(tree: HTMLParser, fallback: str) -> str:
    el = tree.css_first("#partnumber")
    if el is not None:
        sku = (el.attributes.get("data-partnumber") or "").strip()
        if sku:
            return sku
    return fallback


_BG_IMAGE_RE = re.compile(r"url\(['\"]?(.*?)['\"]?\)")


def _extract_gallery_images(tree: HTMLParser) -> list[str]:
    gallery = tree.css_first(".product-gallery")
    if gallery is None:
        return []
    indexed: list[tuple[int, str]] = []
    for i, item in enumerate(gallery.css(".product-image-carousel .carousel-item")):
        thumb = item.css_first(".product_thumbnail")
        if thumb is None:
            continue
        style = thumb.attributes.get("style") or ""
        match = _BG_IMAGE_RE.search(style)
        if not match:
            continue
        raw_index = item.attributes.get("data-fresco-index")
        index = int(raw_index) if raw_index and raw_index.isdigit() else i
        indexed.append((index, _clean_url(match.group(1))))
    indexed.sort(key=lambda pair: pair[0])
    return [url for _, url in indexed]


def _extract_videos(product_data: dict) -> list[str]:
    videos = product_data.get("videos") or {}
    urls = []
    for video_id, info in videos.items():
        if (info or {}).get("source", "").lower() == "youtube":
            urls.append(f"https://www.youtube.com/watch?v={video_id}")
        else:
            urls.append(video_id)
    return urls


def _tab_content(tree: HTMLParser, title: str):
    """Find the `.row-contents` sibling of the collapsible button whose
    `.collapsible-title` matches `title` (Overview / Specs / Emissions / ...)."""
    for button in tree.css("button.collapsible"):
        heading = button.css_first(".collapsible-title")
        if heading is None or heading.text(strip=True).lower() != title.lower():
            continue
        sibling = button.next
        while sibling is not None and sibling.tag == "-text":
            sibling = sibling.next
        return sibling
    return None


def _extract_overview_html(tree: HTMLParser) -> str:
    content = _tab_content(tree, "Overview")
    if content is None:
        return ""
    desc = content.css_first(".full_description")
    return (desc.html or "").strip() if desc is not None else ""


def _extract_specs(tree: HTMLParser) -> dict[str, str]:
    content = _tab_content(tree, "Specs")
    if content is None:
        return {}
    specs: dict[str, str] = {}
    for row in content.css("table.attributes-table tr"):
        label = row.css_first("th.label")
        data = row.css_first("td.data")
        if label is None or data is None:
            continue
        key = label.text(strip=True)
        if key:
            specs[key] = data.text(strip=True)
    return specs


def _extract_emissions(tree: HTMLParser) -> str:
    content = _tab_content(tree, "Emissions")
    if content is None:
        return ""
    return _clean_text(content.text(separator=" ", strip=True))


def _extract_tech_resources(tree: HTMLParser) -> tuple[str | None, list[str], list[str]]:
    """Returns (warranty_link, instruction_links, note_texts)."""
    content = _tab_content(tree, "Tech Resources")
    if content is None:
        return None, [], []
    warranty: str | None = None
    instructions: list[str] = []
    notes: list[str] = []
    for widget in content.css(".widget_info"):
        link = widget.css_first("a[href]")
        if link is not None:
            href = _clean_url(link.attributes.get("href") or "")
            title = (link.attributes.get("title") or link.text(strip=True) or "").strip()
            if title.lower().startswith("warranty"):
                warranty = href
            elif href:
                instructions.append(href)
        else:
            text_el = widget.css_first(".widget_text")
            text = (text_el or widget).text(strip=True)
            if text:
                notes.append(text)
    return warranty, instructions, notes


def _extract_categories(product_data: dict) -> list[str]:
    names = []
    for cat in product_data.get("categories") or []:
        name = cat.get("navnamehierarchy") or cat.get("namehierarchy")
        if name:
            names.append(name)
    return names


def parse_product_page(html: str, url: str) -> FlowmasterRow:
    tree = HTMLParser(html)
    data = _extract_product_data(html)

    brand = data.get("brand") or ""
    sku = _extract_sku(tree, data.get("partnumber") or "")
    title = _extract_title(tree) or (data.get("name") or "").strip()
    if not title:
        title = f"{brand} {sku}".strip()

    warranty, instructions, notes = _extract_tech_resources(tree)
    quantity = data.get("quantity") or 0
    price = _extract_price(tree)
    if price is None:
        price = data.get("price")

    return FlowmasterRow(
        sku=sku,
        title=title,
        url=url,
        breadcrumbs=_extract_breadcrumbs(tree),
        brand=brand,
        short_description=_extract_short_description(tree),
        stock_status=_extract_stock_status(tree),
        in_stock=bool(quantity) and (data.get("lifecycleStatus") != "obsolete"),
        quantity=quantity,
        price=price,
        lifecycle_status=data.get("lifecycleStatus") or "",
        categories=_extract_categories(data),
        images=_extract_gallery_images(tree),
        videos=_extract_videos(data),
        overview_html=_extract_overview_html(tree),
        specs=_extract_specs(tree),
        emissions=_extract_emissions(tree),
        instruction_warranty=warranty,
        instructions=instructions,
        notes=notes,
        created_at=data.get("created"),
        updated_at=data.get("lastmodified"),
    )


async def fetch_product(client: Client, url: str) -> FlowmasterRow:
    html = await client.get_text(url)
    return parse_product_page(html, url)
