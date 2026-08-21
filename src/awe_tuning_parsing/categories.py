"""Discover the site's category taxonomy from the header navigation menu.

We deliberately crawl `nav.header__inline-menu` instead of guessing collection
handles: it's the same taxonomy a human visitor uses, so products end up
classified by vehicle brand (Audi, BMW, ...) and by product type (Exhausts,
Intakes, ...) exactly as the store organizes them.
"""
from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

from selectolax.parser import HTMLParser

from core.http_client import Client

from .config import settings
from .models import Category

log = logging.getLogger(__name__)

# Top-level nav entries that link to real content collections, not info pages.
_SKIP_GROUPS = {"about us", "awe life"}


def _handle_from_href(href: str) -> str | None:
    path = urlparse(href).path
    if "/collections/" not in path:
        return None
    handle = path.split("/collections/", 1)[1].strip("/")
    if not handle or "/" in handle:
        return None
    return handle


def parse_categories(html: str) -> list[Category]:
    tree = HTMLParser(html)
    nav = tree.css_first("nav.header__inline-menu")
    if nav is None:
        raise RuntimeError("header__inline-menu not found - site markup may have changed")

    categories: dict[str, Category] = {}
    for top_li in nav.css("ul.list-menu--inline > li.menu-lv-1"):
        top_link = top_li.css_first("a.menu-lv-1__action")
        if top_link is None:
            continue
        group = top_link.text(strip=True)
        if group.lower() in _SKIP_GROUPS:
            continue

        sub_links = top_li.css("ul a, .megamenu a")
        if not sub_links:
            # Top-level item is itself a collection link (e.g. "Exhausts").
            href = top_link.attributes.get("href") or ""
            handle = _handle_from_href(urljoin(settings.base_url, href))
            if handle:
                categories[handle] = Category(
                    label=group, handle=handle, group=group, kind="product_type"
                )
            continue

        kind = "vehicle" if group.lower() == "vehicles" else "product_type"
        for a in sub_links:
            href = a.attributes.get("href") or ""
            handle = _handle_from_href(urljoin(settings.base_url, href))
            if not handle:
                continue
            label = a.text(strip=True)
            if label.lower().startswith("go to"):
                continue
            categories.setdefault(
                handle, Category(label=label, handle=handle, group=group, kind=kind)
            )

    log.info("discovered %d categories from header nav", len(categories))
    return list(categories.values())


async def fetch_categories(client: Client) -> list[Category]:
    html = await client.get_text(settings.base_url + "/")
    return parse_categories(html)
