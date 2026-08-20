"""Command-line entry point: `uv run main.py` or `uv run awe-tuning-parsing`."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler

from . import pipeline

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
    categories: list[str] = typer.Option(
        None, "--category", "-c", help="Limit to these collection handles (e.g. audi bmw exhaust). Repeatable."
    ),
    skip_details: bool = typer.Option(
        False,
        "--skip-details",
        help="Skip per-product page + fitment fetch (tabs/description/auto columns will be empty). Faster for quick checks.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Scrape the AWE Tuning catalog and save it to data/products.jsonl + data/products.xlsx."""
    _configure_logging(verbose)
    category_filter = set(categories) if categories else None

    async def _run():
        products = await pipeline.run(category_filter)
        if skip_details:
            return pipeline.rows_without_details(products)
        return await pipeline.enrich_and_explode(products)

    rows = asyncio.run(_run())
    jsonl_path, xlsx_path = pipeline.save(rows)

    console.print(f"[green]Saved {len(rows)} variant rows[/green]")
    console.print(f"  JSONL: {jsonl_path}")
    console.print(f"  Excel: {xlsx_path}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
