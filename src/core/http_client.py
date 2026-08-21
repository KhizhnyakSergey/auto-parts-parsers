"""Thin async HTTP wrapper around curl_cffi with polite concurrency + retry."""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from curl_cffi.requests import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

log = logging.getLogger(__name__)


class RetryableStatus(Exception):
    """Raised for transient HTTP statuses (429/5xx) so tenacity can retry."""

    def __init__(self, status_code: int, url: str):
        self.status_code = status_code
        self.url = url
        super().__init__(f"HTTP {status_code} for {url}")


class Client:
    """Wraps a single shared curl_cffi AsyncSession with a semaphore + retry policy.

    Site-agnostic: takes that site's `settings` object (concurrency/timeout/
    request_delay/max_retries/impersonate_pool, and optionally cookies/
    user_agent/effective_impersonate_pool - see flowmaster.config for those)
    so each site's pipeline supplies its own tuning.
    """

    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self._session: AsyncSession | None = None
        self._semaphore = asyncio.Semaphore(self._settings.concurrency)
        # Built per-instance (not a class-level @retry decorator) so
        # max_retries can vary by settings object instead of being frozen to
        # the AWE default at class-definition time.
        self._request = retry(
            retry=retry_if_exception_type(RetryableStatus),
            wait=wait_exponential_jitter(initial=2, max=45),
            stop=stop_after_attempt(self._settings.max_retries),
            reraise=True,
        )(self._request_once)

    async def __aenter__(self) -> "Client":
        # Product pages content-negotiate on Accept and will serve their .json
        # representation instead of HTML if json is preferred - explicit .json
        # endpoints (products.json, collections/*.json) return JSON regardless,
        # so a browser-like HTML-first Accept header works for everything.
        self._session = AsyncSession(
            timeout=self._settings.timeout,
            headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
        )
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._session is not None:
            await self._session.close()

    async def _request_once(self, method: str, url: str, **kwargs: Any):
        assert self._session is not None, "Client must be used as an async context manager"
        # A fresh random pick each call (including retries) spreads requests
        # across fingerprints instead of hammering the WAF with just one - and
        # means a 429 on one fingerprint's retry will likely land on another.
        pool = getattr(self._settings, "effective_impersonate_pool", None) or self._settings.impersonate_pool
        impersonate = random.choice(pool)

        # Cookies/User-Agent are read fresh from `settings` on every single
        # call (not baked into the session once at __aenter__) so a reactive
        # mid-run cookie refresh (flowmaster.clearance.refresh_if_stale)
        # takes effect on the very next request - no session recreation
        # needed. A settings object can optionally carry a captured browser
        # session (cf_clearance/__cf_bm cookies + matching User-Agent) for
        # sites where TLS impersonation alone isn't reliably clearing
        # Cloudflare - see flowmaster.config.Settings.cookies.
        cookies = getattr(self._settings, "cookies", None)
        if cookies:
            kwargs.setdefault("cookies", cookies)
        user_agent = getattr(self._settings, "user_agent", None)
        if user_agent:
            headers = dict(kwargs.get("headers") or {})
            headers.setdefault("User-Agent", user_agent)
            kwargs["headers"] = headers

        async with self._semaphore:
            if self._settings.request_delay:
                await asyncio.sleep(self._settings.request_delay)
            response = await self._session.request(method, url, impersonate=impersonate, **kwargs)
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableStatus(response.status_code, url)
        response.raise_for_status()
        return response

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        response = await self._request("GET", url, **kwargs)
        return response.json()

    async def get_text(self, url: str, **kwargs: Any) -> str:
        response = await self._request("GET", url, **kwargs)
        return response.text

    async def post_json(self, url: str, **kwargs: Any) -> Any:
        response = await self._request("POST", url, **kwargs)
        return response.json()
