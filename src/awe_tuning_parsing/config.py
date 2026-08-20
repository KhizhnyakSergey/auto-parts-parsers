"""Runtime settings for the scraper, overridable via .env or environment variables."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AWE_", env_file=".env", extra="ignore")

    base_url: str = "https://www.awe-tuning.com"
    """Store root; all collection/product JSON endpoints are resolved against this."""

    concurrency: int = 2
    """Max number of in-flight HTTP requests. Keep modest to stay polite to the store.

    Product pages + the third-party fitment endpoint are noticeably more
    429-prone than the plain collections/products.json calls, so this is
    lower than a JSON-only crawl could get away with.
    """

    request_delay: float = 0.6
    """Extra seconds slept before each request (on top of concurrency limiting)."""

    page_size: int = 250
    """Shopify's products.json hard cap per page is 250."""

    timeout: float = 20.0
    max_retries: int = 6

    impersonate_pool: list[str] = [
        "safari18_0",
        "safari17_0",
        "firefox133",
        "firefox135",
        "edge101",
    ]
    """Browser TLS/JA3 fingerprints to rotate through, one picked at random per
    request. The store's WAF progressively rate-limited every Chrome-family
    fingerprint we tried (generic "chrome", then "chrome131", then "chrome120")
    once enough traffic came from it, while Safari/Firefox/Edge stayed clean -
    so the pool deliberately excludes Chrome, and spreads load across several
    fingerprints instead of hammering WAF with just one.
    """

    output_dir: Path = Path("data")
    jsonl_filename: str = "products.jsonl"
    xlsx_filename: str = "products.xlsx"

    excluded_categories: set[str] = {"gear-accessories"}
    """Collection handles skipped entirely on a full scrape (merch, not tuning parts)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.output_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
