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

from .config import settings

log = logging.getLogger(__name__)


class RetryableStatus(Exception):
    """Raised for transient HTTP statuses (429/5xx) so tenacity can retry."""

    def __init__(self, status_code: int, url: str):
        self.status_code = status_code
        self.url = url
        super().__init__(f"HTTP {status_code} for {url}")


class Client:
    """Wraps a single shared curl_cffi AsyncSession with a semaphore + retry policy."""

    def __init__(self) -> None:
        self._session: AsyncSession | None = None
        self._semaphore = asyncio.Semaphore(settings.concurrency)

    async def __aenter__(self) -> "Client":
        self._session = AsyncSession(
            timeout=settings.timeout,
            # Product pages content-negotiate on Accept and will serve their .json
            # representation instead of HTML if json is preferred - explicit .json
            # endpoints (products.json, collections/*.json) return JSON regardless,
            # so a browser-like HTML-first Accept header works for everything.
            headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
        )
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._session is not None:
            await self._session.close()

    @retry(
        retry=retry_if_exception_type(RetryableStatus),
        wait=wait_exponential_jitter(initial=2, max=45),
        stop=stop_after_attempt(settings.max_retries),
        reraise=True,
    )
    async def _get(self, url: str, **kwargs: Any):
        assert self._session is not None, "Client must be used as an async context manager"
        # A fresh random pick each call (including retries) spreads requests
        # across fingerprints instead of hammering the WAF with just one - and
        # means a 429 on one fingerprint's retry will likely land on another.
        impersonate = random.choice(settings.impersonate_pool)
        async with self._semaphore:
            if settings.request_delay:
                await asyncio.sleep(settings.request_delay)
            response = await self._session.get(url, impersonate=impersonate, **kwargs)
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableStatus(response.status_code, url)
        response.raise_for_status()
        return response

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        response = await self._get(url, **kwargs)
        return response.json()

    async def get_text(self, url: str, **kwargs: Any) -> str:
        response = await self._get(url, **kwargs)
        return response.text
