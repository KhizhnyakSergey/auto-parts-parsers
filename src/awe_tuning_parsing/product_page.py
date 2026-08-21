"""Parse the parts of a product page that only exist in the rendered HTML, not
the Shopify JSON API: custom info tabs, the formatted description block (with
its "Important Fitment Notes" callout), the "SEE IT IN ACTION" video gallery,
and per-variant title/sku/price for products that render a variant-comparison
grid. (Variant photos come straight from Shopify's product JSON instead -
see pipeline._variant_images - which tags each image with its variant IDs
directly, no HTML-guessing needed.)

The `#custom-product-tabs` container is empty in the raw HTML - it's filled in
by client-side JS from a `const data = {"tabs": [...]}` blob further down the
page. We read that blob directly instead of running a browser.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from selectolax.parser import HTMLParser

from core.http_client import Client

from .description import html_to_text

log = logging.getLogger(__name__)

_PROP65_MARKER = "prop65"
_FITMENT_NOTES_PREFIX = "important fitment notes"
_DETAILS_SELECTOR = ".halo-productView-right.productView-details.clearfix"
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_VIDEO_GALLERY_SELECTOR = ".video-tab-gallery__container"


def _clean_text(node) -> str:
    return re.sub(r"\s+", " ", node.text(separator=" ", strip=True)).strip()


@dataclass
class VariantHtml:
    variant_id: int
    title: str
    sku: str
    price: float | None
    compare_at_price: float | None


@dataclass
class ProductPageData:
    tabs: dict[str, str] = field(default_factory=dict)
    """Tab title -> raw HTML content, excluding "Installation Instructions"."""
    instruction_links: list[str] = field(default_factory=list)
    details_text: str = ""
    fitment_notes: str = ""
    variants: dict[int, VariantHtml] = field(default_factory=dict)
    video_links: list[str] = field(default_factory=list)
    """Video links from the "SEE IT IN ACTION" gallery (product + customer
    videos combined, in on-page order) - product-level, same for every variant."""


def _extract_tabs_json(html: str) -> list[dict]:
    start = html.find("const data")
    if start == -1:
        return []
    brace_start = html.find("{", start)
    if brace_start == -1:
        return []

    depth = 0
    in_str = False
    esc = False
    i = brace_start
    while i < len(html):
        c = html[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
        i += 1
    else:
        return []

    raw = html[brace_start : i + 1]
    raw = re.sub(r",\s*([\]}])", r"\1", raw)  # trailing commas aren't valid JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("could not parse product tabs JSON blob")
        return []
    return data.get("tabs", [])


def _extract_instruction_links(content_html: str) -> list[str]:
    tree = HTMLParser(content_html)
    links = []
    for a in tree.css("a[href]"):
        href = (a.attributes.get("href") or "").strip()
        if href and _PROP65_MARKER not in href.lower():
            links.append(href)
    return links


def _extract_details(tree: HTMLParser) -> tuple[str, str]:
    """Return (details_text, fitment_notes). Scoped to `.productView-moreItem`
    children only - the container also holds a variant-filter widget (dropdowns,
    CSS) that isn't part of the product description.

    Fitment notes are matched at the `<p>`/`<li>` level with space-joined text,
    not `details_text`'s newline-per-node text: real markup nests the notes as
    `<p><strong>Important Fitment Notes:</strong><br>The rest...</p>`, and
    line-splitting that would cut the sentence apart right after the label.
    """
    block = tree.css_first(_DETAILS_SELECTOR)
    if block is None:
        return "", ""

    texts = []
    fitment_notes = ""
    for item in block.css(".productView-moreItem"):
        text = html_to_text(item.html or "")
        if text:
            texts.append(text)
        for p in item.css("p, li"):
            candidate = _clean_text(p)
            if not candidate.lower().startswith(_FITMENT_NOTES_PREFIX):
                continue
            # A label-only paragraph ("<p><strong>Important Fitment Notes:</strong></p>")
            # is often followed by a <ul> holding the actual notes, rather than the
            # notes being inline in the same element.
            label_only = candidate.strip(" : ").lower() == _FITMENT_NOTES_PREFIX.rstrip(":")
            if label_only:
                parts = [candidate]
                sibling = p.next
                while sibling is not None and sibling.tag not in _HEADING_TAGS:
                    sibling_text = _clean_text(sibling)
                    if sibling_text:
                        parts.append(sibling_text)
                    sibling = sibling.next
                fitment_notes = " ".join(parts)
            else:
                fitment_notes = candidate
    return "\n\n".join(texts), fitment_notes


def _parse_price(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"[\d,]+\.\d{2}", text)
    if not match:
        return None
    return float(match.group().replace(",", ""))


def _extract_variant_htmls(tree: HTMLParser) -> dict[int, VariantHtml]:
    result: dict[int, VariantHtml] = {}
    for section in tree.css("section.product-variants__variant"):
        raw_id = section.attributes.get("id") or ""
        if not raw_id.startswith("var-") or not raw_id[4:].isdigit():
            continue
        variant_id = int(raw_id[4:])

        title_el = section.css_first(".product-variant__title")
        sku_el = section.css_first(".product-variant__sku")
        price_el = section.css_first(".product-variants__variant-price .price")
        compare_el = section.css_first(".product-variants__variant-price .compare-price")

        result[variant_id] = VariantHtml(
            variant_id=variant_id,
            title=title_el.text(strip=True) if title_el else "",
            sku=(sku_el.attributes.get("data-sku") if sku_el else "") or "",
            price=_parse_price(price_el.text(strip=True) if price_el else None),
            compare_at_price=_parse_price(compare_el.text(strip=True) if compare_el else None),
        )
    return result


def _extract_video_links(tree: HTMLParser) -> list[str]:
    block = tree.css_first(_VIDEO_GALLERY_SELECTOR)
    if block is None:
        return []
    links: list[str] = []
    seen: set[str] = set()
    for a in block.css("a[href]"):
        href = (a.attributes.get("href") or "").strip()
        if href and href not in seen:
            seen.add(href)
            links.append(href)
    return links


def parse_product_page(html: str) -> ProductPageData:
    tree = HTMLParser(html)
    data = ProductPageData()

    for tab in _extract_tabs_json(html):
        title = (tab.get("title") or "").strip()
        content = tab.get("content") or ""
        if not title:
            continue
        if title.lower() == "installation instructions":
            data.instruction_links = _extract_instruction_links(content)
        else:
            data.tabs[title] = content

    data.details_text, data.fitment_notes = _extract_details(tree)
    data.variants = _extract_variant_htmls(tree)
    data.video_links = _extract_video_links(tree)
    return data


async def fetch_product_page(client: Client, url: str) -> ProductPageData:
    html = await client.get_text(url)
    return parse_product_page(html)
