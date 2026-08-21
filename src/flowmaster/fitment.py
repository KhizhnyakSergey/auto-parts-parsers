"""Vehicle fitment ("Vehicle Applications") data.

Not present in the raw product-page HTML - filled in client-side via a POST
to the site's own `/assets/php/producthelpers.php`, which returns *facets*
(independent per-field option lists with counts), not a flat table: querying
with no filters returns marginal counts for year/make/model/... that don't
say which combinations are actually valid together (e.g. "Tahoe" only exists
under Chevrolet, never GMC; year coverage differs per model too).

To reconstruct the exact `{year||make||model}` combos - same semantics as the
AWE scraper's `auto` column - this walks the facet tree top-down: make ->
model -> year. That ordering (not year -> make) keeps the number of requests
small, since a part's make/model list is usually tiny even when its year
range spans decades.

The same per-make call that lists models also returns the submodel/engine/
body/transmission facets for that make (aggregated across all its models and
years) - exactly what's needed for the AWE-style grouped-by-make columns, so
no extra requests are needed for those.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from core.http_client import Client

from .config import settings

log = logging.getLogger(__name__)

_ENDPOINT_PATH = "/assets/php/producthelpers.php"
_GROUPED_FACETS = ("submodel", "engine", "body", "transmission")


def _trigger_reactive_refresh() -> None:
    """Fire-and-forget: a failed fitment call is exactly the "something's
    wrong with the cookie" signal refresh_if_stale watches for. Not awaited -
    the failed call has already been logged and skipped, no need to stall
    this drill-down waiting on a ~10-20s browser solve."""
    if settings.auto_refresh_clearance:
        from .clearance import refresh_if_stale

        asyncio.create_task(refresh_if_stale())


@dataclass
class Fitment:
    auto: str | None = None
    submodel: str | None = None
    engine: str | None = None
    body_type: str | None = None
    transmission: str | None = None


def _facet_values(options: dict, key: str) -> list[str]:
    return [item["value"] for item in options.get(key) or [] if item.get("value")]


async def _call(client: Client, endpoint: str, referer: str, partnumber: str, **filters: str) -> dict:
    data = {"action": "get_application_headers", "applicationType": "vehicle", "partnumber": partnumber}
    data.update(filters)
    # A real browser's jQuery.ajax() call sends these XHR-specific headers on
    # top of whatever curl_cffi's TLS impersonation profile already sets for
    # a plain navigation - this endpoint (unlike page GETs) seems to check
    # for them, likely as part of Cloudflare bot-management scoring.
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": referer,
        "Origin": settings.base_url,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    payload = await client.post_json(endpoint, data=data, headers=headers)
    return (payload.get("data") or {}).get("vehicleApplications") or {}


def _format_auto(combos: set[str]) -> str | None:
    return "{" + ",".join(sorted(combos)) + "}" if combos else None


def _format_grouped(groups: dict[str, set[str]]) -> str | None:
    groups = {make: values for make, values in groups.items() if values}
    if not groups:
        return None
    parts = (f"{make}: {{{', '.join(sorted(values))}}}" for make, values in sorted(groups.items()))
    return ", ".join(parts)


async def fetch_fitment(client: Client, partnumber: str, product_url: str) -> Fitment:
    endpoint = f"{settings.base_url}{_ENDPOINT_PATH}"
    try:
        root = await _call(client, endpoint, product_url, partnumber)
    except Exception:
        log.warning("fitment lookup failed for partnumber %s", partnumber, exc_info=True)
        _trigger_reactive_refresh()
        return Fitment()

    makes = _facet_values(root.get("options") or {}, "make")
    if not makes:
        return Fitment()

    combos: set[str] = set()
    grouped: dict[str, dict[str, set[str]]] = {name: {} for name in _GROUPED_FACETS}

    for make in makes:
        try:
            by_make = await _call(client, endpoint, product_url, partnumber, vehicleMake=make)
        except Exception:
            log.warning("fitment lookup failed for %s / make=%s", partnumber, make, exc_info=True)
            _trigger_reactive_refresh()
            continue

        options = by_make.get("options") or {}
        for facet in _GROUPED_FACETS:
            values = {v for v in _facet_values(options, facet) if v.upper() != "N/A"}
            if values:
                grouped[facet][make] = values

        for model in _facet_values(options, "model"):
            try:
                by_model = await _call(
                    client, endpoint, product_url, partnumber, vehicleMake=make, vehicleModel=model
                )
            except Exception:
                log.warning(
                    "fitment lookup failed for %s / make=%s model=%s", partnumber, make, model, exc_info=True
                )
                _trigger_reactive_refresh()
                continue
            for year in _facet_values(by_model.get("options") or {}, "year"):
                combos.add(f"{year}||{make}||{model}")

    return Fitment(
        auto=_format_auto(combos),
        submodel=_format_grouped(grouped["submodel"]),
        engine=_format_grouped(grouped["engine"]),
        body_type=_format_grouped(grouped["body"]),
        transmission=_format_grouped(grouped["transmission"]),
    )
