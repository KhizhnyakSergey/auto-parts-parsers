"""Orchestrates the full scrape: discover categories, fetch products per category, merge, save."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from rich.progress import Progress

from .categories import fetch_categories
from .compatibility import build_variant_fitment, fetch_compatibility_table
from core.http_client import Client

from .config import settings
from .models import Category, Product, ProductRow, Variant
from .product_page import ProductPageData, fetch_product_page
from .products import build_product, iter_all_products, iter_collection_products
from .storage import write_jsonl, write_xlsx

log = logging.getLogger(__name__)


async def _collect_category(
    client: Client, category: Category, products: dict[int, Product], lock: asyncio.Lock, progress: Progress, task_id
) -> None:
    count = 0
    try:
        async for raw in iter_collection_products(client, category.handle):
            product = build_product(raw)
            async with lock:
                existing = products.get(product.id)
                if existing is None:
                    existing = product
                    products[product.id] = existing
                if category.label not in existing.categories:
                    existing.categories.append(category.label)
                if category.kind == "vehicle" and category.label not in existing.vehicle_brands:
                    existing.vehicle_brands.append(category.label)
            count += 1
        progress.update(task_id, advance=1, description=f"[cyan]{category.label}[/cyan] ({count} products)")
    except Exception:
        # One flaky category (e.g. a 429 that outlasted retries) shouldn't sink
        # the whole run - log it and keep whatever other categories found.
        log.warning("failed to scrape category %s (kept %d products from it)", category.handle, count, exc_info=True)
        progress.update(task_id, advance=1, description=f"[red]{category.label} FAILED[/red]")


async def _collect_ids(client: Client, handle: str, ids: set[int]) -> None:
    try:
        async for raw in iter_collection_products(client, handle):
            ids.add(raw["id"])
    except Exception:
        log.warning("failed to list excluded category %s", handle, exc_info=True)


async def run(category_filter: set[str] | None = None) -> list[Product]:
    """Scrape the whole catalog. `category_filter`, if given, limits to these collection handles.

    Categories in `settings.excluded_categories` (e.g. gear-accessories merch) are
    skipped, unless explicitly named in `category_filter` - an explicit request wins.
    """
    products: dict[int, Product] = {}
    lock = asyncio.Lock()
    excluded_handles = settings.excluded_categories - (category_filter or set())

    async with Client(settings) as client:
        categories = await fetch_categories(client)
        if category_filter:
            categories = [c for c in categories if c.handle in category_filter]

        active = [c for c in categories if c.handle not in excluded_handles]
        skipped = [c for c in categories if c.handle in excluded_handles]
        if skipped:
            log.info("skipping excluded categories: %s", ", ".join(c.handle for c in skipped))
        log.info("scraping %d categories", len(active))

        # Products listed only under an excluded category must stay excluded from
        # the gap-fill pass below too, not silently reappear as "uncategorized".
        excluded_ids: set[int] = set()
        await asyncio.gather(*(_collect_ids(client, c.handle, excluded_ids) for c in skipped))

        with Progress() as progress:
            task_id = progress.add_task("Scraping categories...", total=len(active))
            await asyncio.gather(
                *(
                    _collect_category(client, category, products, lock, progress, task_id)
                    for category in active
                )
            )

        if category_filter is None:
            # A handful of products aren't linked from any header-nav collection
            # (discontinued items, test/service entries). Sweep the global
            # catalog so a full run doesn't silently drop them.
            gap_filled = 0
            try:
                async for raw in iter_all_products(client):
                    if raw["id"] in excluded_ids:
                        continue
                    product = build_product(raw)
                    if product.id not in products:
                        products[product.id] = product
                        gap_filled += 1
            except Exception:
                log.warning("gap-fill pass over the global catalog failed partway through", exc_info=True)
            if gap_filled:
                log.info("added %d products not linked from any nav category", gap_filled)

    result = sorted(products.values(), key=lambda p: p.id)
    log.info("collected %d unique products", len(result))
    return result


def _variant_images(product: Product, variant: Variant) -> list[str]:
    """Primary photo first (Image 1), then the rest of this variant's photos.

    Shopify's own product JSON already tags each image with the variant IDs
    it belongs to (`image.variant_ids`) and each variant with its featured
    image (`variant.image_id`) - authoritative, no filename-guessing needed.
    An empty `variant_ids` means the photo is generic/shared and Shopify shows
    it for every variant, so we include those too.
    """
    by_id = {img.id: img for img in product.images}
    images: list[str] = []
    seen: set[int] = set()

    primary = by_id.get(variant.image_id) if variant.image_id else None
    if primary is None and product.images:
        primary = product.images[0]
    if primary is not None:
        images.append(primary.src)
        seen.add(primary.id)

    for img in product.images:
        if img.id in seen:
            continue
        if not img.variant_ids or variant.id in img.variant_ids:
            images.append(img.src)
            seen.add(img.id)
    return images


def _row_from_variant(
    product: Product, variant: Variant, page_data: ProductPageData | None, compat_rows: list
) -> ProductRow:
    html_v = page_data.variants.get(variant.id) if page_data else None
    fitment = build_variant_fitment(compat_rows, variant.sku)

    return ProductRow(
        product_id=product.id,
        variant_id=variant.id,
        title=(html_v.title if html_v and html_v.title else product.title),
        sku=variant.sku,
        url=product.url,
        vendor=product.vendor,
        product_type=product.product_type,
        categories=product.categories,
        vehicle_brands=product.vehicle_brands,
        tags=product.tags,
        price=(html_v.price if html_v and html_v.price is not None else variant.price),
        compare_at_price=(html_v.compare_at_price if html_v else variant.compare_at_price),
        currency=product.currency,
        in_stock=variant.available,
        images=_variant_images(product, variant),
        description=product.description,
        details_text=page_data.details_text if page_data else "",
        important_fitment_notes=page_data.fitment_notes if page_data else "",
        tabs=page_data.tabs if page_data else {},
        instruction_links=page_data.instruction_links if page_data else [],
        video_links=page_data.video_links if page_data else [],
        auto=fitment.auto,
        submodel=fitment.submodel,
        engine=fitment.engine,
        body_type=fitment.body_type,
        bed_length=fitment.bed_length,
        variant_fits_html=fitment.html,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


async def _explode_product(
    client: Client, product: Product, rows: list[ProductRow], progress: Progress, task_id
) -> None:
    try:
        page_data = await fetch_product_page(client, product.url)
    except Exception:
        log.warning("failed to fetch product page for %s", product.handle, exc_info=True)
        page_data = None

    compat_rows = await fetch_compatibility_table(client, product.id)
    for variant in product.variants:
        rows.append(_row_from_variant(product, variant, page_data, compat_rows))
    progress.update(task_id, advance=1, description=f"[cyan]{product.handle}[/cyan]")


async def enrich_and_explode(products: list[Product]) -> list[ProductRow]:
    """For each unique product, fetch its page (tabs/description/variant HTML)
    and its fitment table, then explode it into one ProductRow per variant."""
    rows: list[ProductRow] = []

    async with Client(settings) as client:
        with Progress() as progress:
            task_id = progress.add_task("Fetching product pages & fitment...", total=len(products))
            await asyncio.gather(
                *(_explode_product(client, product, rows, progress, task_id) for product in products)
            )

    rows.sort(key=lambda r: (r.product_id, r.variant_id))
    log.info("exploded %d products into %d variant rows", len(products), len(rows))
    return rows


def rows_without_details(products: list[Product]) -> list[ProductRow]:
    """Explode into ProductRow without fetching product pages/fitment - tabs,
    details_text and the fitment columns stay empty. Useful for quick checks."""
    return [
        _row_from_variant(product, variant, None, [])
        for product in products
        for variant in product.variants
    ]


def save(rows: list[ProductRow]) -> tuple[Path, Path]:
    jsonl_path = settings.output_dir / settings.jsonl_filename
    xlsx_path = settings.output_dir / settings.xlsx_filename
    write_jsonl(rows, jsonl_path)
    write_xlsx(rows, xlsx_path)
    return jsonl_path, xlsx_path
