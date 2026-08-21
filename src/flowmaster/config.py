"""Runtime settings for the Flowmaster scraper, overridable via .env or environment variables."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FLOWMASTER_", env_file=".env", extra="ignore")

    base_url: str = "https://www.flowmastermufflers.com"

    sitemaps: list[str] = ["exhaust", "air_intakes_and_filters", "discontinued"]
    """Names under /sitemap_products/{name}/ to crawl for product URLs. Other
    entries in the site's sitemap index (deals, merch, car_care, ...) are either
    excluded product lines or just category/landing pages, not products."""

    concurrency: int = 2
    request_delay: float = 0.6
    timeout: float = 20.0
    max_retries: int = 6

    impersonate_pool: list[str] = [
        "safari18_0",
        "safari17_0",
        "firefox133",
        "firefox135",
        "edge101",
    ]
    """Browser TLS/JA3 fingerprints to rotate through when no `cf_clearance`
    cookie is set. TLS impersonation alone gets past this site's Cloudflare
    Managed Challenge most of the time, but - unlike AWE's WAF - not always
    reliably: under sustained load the site can keep soft-blocking plain
    impersonated requests (429s and re-issued challenge pages) even well
    after backing off, while a real `cf_clearance` cookie from a browser
    that solved the challenge gets through cleanly. See `cf_clearance` below."""

    cf_clearance: str | None = None
    cf_bm: str | None = None
    shopping_cart: str | None = None
    extra_cookies: dict[str, str] = {}
    """Any other cookie a real browser picked up while solving the challenge
    (e.g. cf_chl_rc_ni, g_state) - captured by clearance.py alongside the
    named ones above, in case the fitment AJAX endpoint checks for more than
    just cf_clearance."""
    user_agent: str | None = None
    """Optional cookies + matching User-Agent captured from a real browser
    that solved the Cloudflare challenge (devtools -> Application -> Cookies,
    or a captured request's headers). Set via .env
    (FLOWMASTER_CF_CLEARANCE / FLOWMASTER_CF_BM / FLOWMASTER_USER_AGENT) for
    a large run if plain TLS impersonation is getting soft-blocked. Never
    commit real values - .env is gitignored for this reason. cf_clearance
    expires (observed lifetime: well under a day) and is tied to the browser
    that solved the challenge, so `clearance_impersonate_pool` below is used
    instead of `impersonate_pool` whenever it's set."""

    clearance_impersonate_pool: list[str] = ["chrome131", "chrome124", "chrome120"]
    """Used instead of `impersonate_pool` when `cf_clearance` is set - the
    cookie is bound to the Chrome-family browser that solved the challenge,
    so impersonating Safari/Firefox alongside it would mismatch and likely
    get rejected."""

    auto_refresh_clearance: bool = True
    """Solve the Cloudflare challenge with a real headless browser (see
    clearance.py) at the start of every run, overwriting cf_clearance/cf_bm/
    user_agent above - no more manually copying cookies out of devtools.
    Set FLOWMASTER_AUTO_REFRESH_CLEARANCE=false to skip this (e.g. no Chrome
    available) and rely on whatever's in .env, or plain TLS impersonation."""

    output_dir: Path = Path("data")
    jsonl_filename: str = "flowmaster_products.jsonl"
    xlsx_filename: str = "flowmaster_products.xlsx"

    @property
    def cookies(self) -> dict[str, str]:
        cookies = dict(self.extra_cookies)
        if self.cf_clearance:
            cookies["cf_clearance"] = self.cf_clearance
        if self.cf_bm:
            cookies["__cf_bm"] = self.cf_bm
        if self.shopping_cart:
            cookies["ShoppingCart"] = self.shopping_cart
        return cookies

    @property
    def effective_impersonate_pool(self) -> list[str]:
        return self.clearance_impersonate_pool if self.cf_clearance else self.impersonate_pool

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.output_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
