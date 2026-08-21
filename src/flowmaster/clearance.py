"""Automatically solve the site's Cloudflare challenge with a real headless
browser (botasaurus), instead of requiring a `cf_clearance` cookie manually
copied out of devtools.

TLS impersonation alone (see http_client.py) clears the initial challenge
most of the time, but under sustained scraping volume the site can keep
soft-blocking impersonated requests even with a previously-valid clearance
cookie - a real solved-by-an-actual-browser session holds up much better.
Solving only takes a few seconds, so `pipeline.run()` just does this once at
the start of every run rather than trying to detect staleness.
"""
from __future__ import annotations

import asyncio
import logging
import time

from botasaurus.browser import Driver, browser

from .config import settings

log = logging.getLogger(__name__)

_MIN_REFRESH_INTERVAL = 120.0
"""Floor between reactive refreshes (see refresh_if_stale) - a burst of
requests failing around the same time (many concurrent workers) should
trigger one browser solve, not one per failure."""

_last_refresh_at = 0.0
_refresh_lock = asyncio.Lock()


_SAMPLE_PRODUCT_URL = "https://www.flowmastermufflers.com/products/exhaust/mufflers/flowfx_mufflers/parts/71225"


_NAV_READY_SELECTOR = "#nav"
_NAV_READY_TIMEOUT = 20


@browser(headless=False, output=None, create_error_logs=False)
def _solve(driver: Driver, data):
    # Landing on an actual product page (not just the homepage) so every
    # cookie/localStorage side effect a real visit triggers (cart init,
    # session id, ...) is present too - the fitment AJAX endpoint may check
    # more than just cf_clearance.
    driver.google_get(_SAMPLE_PRODUCT_URL, bypass_cloudflare=True)
    # A fixed sleep is a guess - the real signal that we're past the
    # challenge and the page actually rendered (not still mid-navigation) is
    # the site's own nav bar showing up in the DOM.
    try:
        driver.wait_for_element(_NAV_READY_SELECTOR, wait=_NAV_READY_TIMEOUT)
    except Exception:
        log.warning(
            "'%s' didn't appear within %ss - page may not have fully loaded, "
            "grabbing cookies anyway",
            _NAV_READY_SELECTOR,
            _NAV_READY_TIMEOUT,
        )
    return {
        "cookies": driver.get_cookies_dict(),
        "user_agent": driver.run_js("return navigator.userAgent"),
    }


def refresh_clearance() -> bool:
    """Solve the Cloudflare challenge and update `settings` in place with a
    fresh cf_clearance/__cf_bm/user_agent and every other cookie the browser
    picked up. Returns False (leaving whatever was already in settings/.env
    untouched) if the browser solve fails - e.g. no Chrome installed - so
    callers can fall back to plain TLS impersonation or a manually-provided
    cookie instead of hard-failing."""
    try:
        result = _solve()
    except Exception:
        log.warning("automatic Cloudflare clearance refresh failed", exc_info=True)
        return False

    cookies = (result or {}).get("cookies") or {}
    if not cookies.get("cf_clearance"):
        log.warning("automatic Cloudflare clearance refresh returned no cf_clearance cookie")
        return False

    settings.cf_clearance = cookies.get("cf_clearance")
    settings.cf_bm = cookies.get("__cf_bm")
    settings.shopping_cart = cookies.get("ShoppingCart")
    settings.extra_cookies = {
        k: v for k, v in cookies.items() if k not in ("cf_clearance", "__cf_bm", "ShoppingCart")
    }
    settings.user_agent = result.get("user_agent")
    log.info("refreshed cf_clearance cookie automatically (%d cookies total)", len(cookies))
    return True


async def refresh_if_stale(min_interval: float = _MIN_REFRESH_INTERVAL) -> None:
    """Call this when a request fails in a way that suggests the cookie died
    (429s, a re-issued challenge page) - re-solves in a background thread
    (the browser solve is a blocking call) so the *next* request picks up a
    fresh cookie, without waiting for a fixed timer.

    Debounced to at most once per `min_interval`: many workers can hit
    failures around the same moment once the cookie actually goes stale, and
    without this they'd each launch their own browser solve concurrently.
    The check-and-stamp happens under the lock (so only one caller "wins"
    per window); the slow browser solve itself runs outside it so losing
    callers return immediately instead of queueing behind it.
    """
    global _last_refresh_at
    async with _refresh_lock:
        now = time.monotonic()
        if now - _last_refresh_at < min_interval:
            return
        _last_refresh_at = now

    log.info("reactive cf_clearance refresh triggered after a request failure")
    await asyncio.to_thread(refresh_clearance)
