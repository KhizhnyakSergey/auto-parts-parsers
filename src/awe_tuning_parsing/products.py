"""Fetch and normalize products from Shopify's public collection JSON endpoints."""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from core.http_client import Client

from .config import settings
from .description import html_to_text
from .models import Image, Product, Variant

log = logging.getLogger(__name__)


async def iter_collection_products(client: Client, handle: str) -> AsyncIterator[dict[str, Any]]:
    """Yield raw product dicts for one collection, paginating until a page comes back empty."""
    url = f"{settings.base_url}/collections/{handle}/products.json"
    async for raw in _paginate(client, url):
        yield raw


async def iter_all_products(client: Client) -> AsyncIterator[dict[str, Any]]:
    """Yield every product in the store's global catalog, paginating /products.json.

    Used as a completeness pass: a handful of products (discontinued items, test
    entries, non-part listings like shipping insurance) aren't linked from any
    header-nav collection, so a purely category-driven crawl misses them.
    """
    async for raw in _paginate(client, f"{settings.base_url}/products.json"):
        yield raw


async def _paginate(client: Client, url: str) -> AsyncIterator[dict[str, Any]]:
    page = 1
    while True:
        data = await client.get_json(url, params={"limit": settings.page_size, "page": page})
        raw_products = data.get("products", [])
        if not raw_products:
            return
        for raw in raw_products:
            yield raw
        if len(raw_products) < settings.page_size:
            return
        page += 1


def build_product(raw: dict[str, Any]) -> Product:
    """Convert a raw Shopify product dict into our normalized model (categories filled in later)."""
    variants = [
        Variant(
            id=v["id"],
            title=v.get("title", ""),
            sku=v.get("sku") or "",
            price=float(v["price"]),
            compare_at_price=float(v["compare_at_price"]) if v.get("compare_at_price") else None,
            available=bool(v.get("available", True)),
            image_id=(v.get("featured_image") or {}).get("id"),
        )
        for v in raw.get("variants", [])
    ]
    images = [
        Image(id=img["id"], src=img["src"], alt=img.get("alt"), variant_ids=img.get("variant_ids", []))
        for img in raw.get("images", [])
    ]
    prices = [v.price for v in variants]

    return Product(
        id=raw["id"],
        title=raw.get("title", ""),
        handle=raw["handle"],
        vendor=raw.get("vendor", ""),
        product_type=raw.get("product_type", ""),
        tags=raw.get("tags", []) if isinstance(raw.get("tags"), list) else [],
        url=f"{settings.base_url}/products/{raw['handle']}",
        description=html_to_text(raw.get("body_html", "")),
        price_min=min(prices) if prices else None,
        price_max=max(prices) if prices else None,
        in_stock=any(v.available for v in variants),
        variants=variants,
        images=images,
        created_at=raw.get("created_at"),
        updated_at=raw.get("updated_at"),
    )
