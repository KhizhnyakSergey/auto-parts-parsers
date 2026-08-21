"""Orchestrates the full Flowmaster scrape: discover product URLs from the
sitemap, fetch each product page + fitment data, dedupe, and save."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from core.http_client import Client
from rich.progress import Progress

from .config import settings
from .fitment import fetch_fitment
from .models import FlowmasterRow
from .product_page import fetch_product
from .sitemap import iter_product_urls
from .storage import append_jsonl, load_jsonl, write_jsonl, write_xlsx

log = logging.getLogger(__name__)

# Each product needs up to ~8 sequential requests (page + fitment drill-down),
# unlike AWE's ~2. A fixed-size pool of worker coroutines pulling from a
# queue - rather than creating one asyncio.Task per product up front (~1600
# of them) - keeps only a handful of products in flight at a time, so each
# one's own requests cycle through the HTTP-level concurrency quickly instead
# of competing with everyone else's, and progress advances steadily instead
# of sitting at 0% until most of the catalog has been touched once.
_WORKER_COUNT = 8


def _sku_from_url(url: str) -> str:
    """Every product URL ends in `/parts/{sku}` and that trailing segment is
    the same value the page's own product_data.partnumber reports - checked
    across every product family (numeric AWE-Tuning-style ids, discontinued's
    alphanumeric legacy skus, etc). Used to filter out already-scraped
    products *before* fetching them on --resume, without needing a request."""
    return url.rstrip("/").rsplit("/", 1)[-1]


async def _worker(
    client: Client,
    queue: "asyncio.Queue[str | None]",
    rows: list[FlowmasterRow],
    jsonl_path: Path,
    progress: Progress,
    task_id,
) -> None:
    while True:
        url = await queue.get()
        if url is None:
            queue.task_done()
            return

        try:
            row = await fetch_product(client, url)
        except Exception:
            log.warning("failed to fetch product page %s", url, exc_info=True)
            progress.update(task_id, advance=1, description=f"[red]FAILED {url}[/red]")
            if settings.auto_refresh_clearance:
                from .clearance import refresh_if_stale

                asyncio.create_task(refresh_if_stale())
            queue.task_done()
            continue

        fitment = await fetch_fitment(client, row.sku, url)
        row.auto = fitment.auto
        row.submodel = fitment.submodel
        row.engine = fitment.engine
        row.body_type = fitment.body_type
        row.transmission = fitment.transmission

        rows.append(row)
        # Written immediately (not just held in memory for the final save())
        # so a crash or Ctrl+C partway through a long run doesn't lose
        # everything scraped so far - a --resume rerun picks up from here.
        append_jsonl(row, jsonl_path)
        progress.update(task_id, advance=1, description=f"[cyan]{row.sku}[/cyan]")
        queue.task_done()


async def run(resume: bool = True) -> list[FlowmasterRow]:
    """Scrape the whole catalog. With `resume` (the default), any product
    already present in data/flowmaster_products.jsonl from a previous run is
    skipped rather than re-fetched - useful since a run can be interrupted
    partway (e.g. an expired cf_clearance cookie). Pass `resume=False` to
    ignore existing output and rescrape everything.
    """
    if settings.auto_refresh_clearance:
        from .clearance import refresh_clearance

        refresh_clearance()

    jsonl_path = settings.output_dir / settings.jsonl_filename
    existing_rows: list[FlowmasterRow] = []
    already_scraped: set[str] = set()
    if resume:
        existing_rows = load_jsonl(jsonl_path)
        already_scraped = {row.sku for row in existing_rows}
        if already_scraped:
            log.info("resuming: %d products already scraped, skipping them", len(already_scraped))

    async with Client(settings) as client:
        urls = await iter_product_urls(client)
        log.info("discovered %d product urls from sitemap", len(urls))

        if already_scraped:
            before = len(urls)
            urls = [u for u in urls if _sku_from_url(u) not in already_scraped]
            log.info("%d of %d urls remain after skipping already-scraped products", len(urls), before)

        queue: "asyncio.Queue[str | None]" = asyncio.Queue()
        for url in urls:
            queue.put_nowait(url)
        for _ in range(_WORKER_COUNT):
            queue.put_nowait(None)  # one stop-sentinel per worker

        rows: list[FlowmasterRow] = list(existing_rows)
        with Progress() as progress:
            task_id = progress.add_task("Scraping products...", total=len(urls))
            workers = [
                asyncio.create_task(_worker(client, queue, rows, jsonl_path, progress, task_id))
                for _ in range(_WORKER_COUNT)
            ]
            await asyncio.gather(*workers)

    deduped: dict[str, FlowmasterRow] = {}
    for row in rows:
        existing = deduped.get(row.sku)
        if existing is not None:
            log.warning("duplicate sku %s: kept %s, dropped %s", row.sku, existing.url, row.url)
            continue
        deduped[row.sku] = row

    result = sorted(deduped.values(), key=lambda r: r.sku)
    log.info("collected %d unique products", len(result))
    return result


def save(rows: list[FlowmasterRow]) -> tuple[Path, Path]:
    """Rewrites data/flowmaster_products.jsonl with the final deduped/sorted
    set (the file already holds this data from `run()`'s incremental
    appends, in scrape order with possible resume-duplicates - this produces
    the clean version) and writes the Excel workbook."""
    jsonl_path = settings.output_dir / settings.jsonl_filename
    xlsx_path = settings.output_dir / settings.xlsx_filename
    write_jsonl(rows, jsonl_path)
    write_xlsx(rows, xlsx_path)
    return jsonl_path, xlsx_path
