"""Discover product URLs via the site's own sitemap, rather than crawling the
category tree.

The category pages (`/products/exhaust/...`) paginate with an undocumented
`?page=N` param and don't expose a total-pages count, so reconstructing the
full catalog by crawling them would mean guessing when to stop. Worse, ~700
discontinued parts live under `/products/discontinued/parts/{sku}` and aren't
linked from the category tree *at all*.

`/sitemap/` is a sitemapindex listing per-line-of-business sitemaps
(`/sitemap_products/{name}/`). Only a few of those actually list product pages
(`exhaust`, `air_intakes_and_filters`, `discontinued` - see `settings.sitemaps`);
the rest (`deals`, `merch`, `car_care`, `signature_series_exhaust`, and all the
`sitemap_platforms/*`) are category/landing pages, not products.
"""
from __future__ import annotations

import logging
import re

from core.http_client import Client

from .config import settings

log = logging.getLogger(__name__)

_LOC_RE = re.compile(r"<loc>(.*?)</loc>")


async def iter_product_urls(client: Client) -> list[str]:
    """Return every product-page URL from `settings.sitemaps`, deduplicated."""
    urls: set[str] = set()
    for name in settings.sitemaps:
        sitemap_url = f"{settings.base_url}/sitemap_products/{name}/"
        try:
            xml = await client.get_text(sitemap_url)
        except Exception:
            log.warning("failed to fetch sitemap %s", name, exc_info=True)
            continue
        locs = [u for u in _LOC_RE.findall(xml) if "/parts/" in u]
        log.info("sitemap %s: %d product urls", name, len(locs))
        urls.update(locs)
    return sorted(urls)
