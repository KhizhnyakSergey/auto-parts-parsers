"""Command-line entry point: `uv run main.py` or `uv run awe-tuning-parsing`."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler

app = typer.Typer(add_completion=False)
console = Console()

_LOGS_DIR = Path("logs")


def _configure_logging(verbose: bool) -> None:
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _LOGS_DIR / f"run-{datetime.now():%Y%m%d-%H%M%S}.log"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s"))

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False), file_handler],
    )


@app.command()
def scrape(
    site: str = typer.Option("awe", "--site", help="Which catalog to scrape: 'awe' or 'flowmaster'."),
    categories: list[str] = typer.Option(
        None,
        "--category",
        "-c",
        help="[awe only] Limit to these collection handles (e.g. audi bmw exhaust). Repeatable.",
    ),
    skip_details: bool = typer.Option(
        False,
        "--skip-details",
        help="[awe only] Skip per-product page + fitment fetch (tabs/description/auto columns will be empty). Faster for quick checks.",
    ),
    fresh: bool = typer.Option(
        False,
        "--fresh",
        help="[flowmaster only] Ignore any existing data/flowmaster_products.jsonl and rescrape everything, instead of skipping already-scraped products.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Scrape a catalog and save it to data/*.jsonl + data/*.xlsx."""
    _configure_logging(verbose)

    if site == "awe":
        from awe_tuning_parsing import pipeline as awe_pipeline

        category_filter = set(categories) if categories else None

        async def _run():
            products = await awe_pipeline.run(category_filter)
            if skip_details:
                return awe_pipeline.rows_without_details(products)
            return await awe_pipeline.enrich_and_explode(products)

        rows = asyncio.run(_run())
        jsonl_path, xlsx_path = awe_pipeline.save(rows)
    elif site == "flowmaster":
        from flowmaster import pipeline as flowmaster_pipeline

        rows = asyncio.run(flowmaster_pipeline.run(resume=not fresh))
        jsonl_path, xlsx_path = flowmaster_pipeline.save(rows)
    else:
        console.print(f"[red]Unknown --site {site!r}. Use 'awe' or 'flowmaster'.[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]Saved {len(rows)} rows[/green]")
    console.print(f"  JSONL: {jsonl_path}")
    console.print(f"  Excel: {xlsx_path}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
