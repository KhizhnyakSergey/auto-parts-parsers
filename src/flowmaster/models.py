"""Data model for one scraped Flowmaster product - one row per product (no
variant explosion: unlike AWE's Shopify catalog, each product page here is a
single sellable SKU)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class FlowmasterRow(BaseModel):
    sku: str
    title: str
    url: str
    breadcrumbs: str = ""
    brand: str = ""
    short_description: str = ""
    stock_status: str = ""
    in_stock: bool = False
    quantity: int = 0
    price: float | None = None
    currency: str = "USD"
    lifecycle_status: str = ""
    """Site's own status field, e.g. "active" or "obsolete" (discontinued parts)."""
    categories: list[str] = Field(default_factory=list)

    images: list[str] = Field(default_factory=list)
    videos: list[str] = Field(default_factory=list)

    overview_html: str = ""
    specs: dict[str, str] = Field(default_factory=dict)
    """Label -> value pairs from the on-page Specs table. The *set* of labels
    differs per product, so these become dynamic Excel columns (like AWE's
    per-product tabs) rather than fixed fields."""
    emissions: str = ""

    instruction_warranty: str | None = None
    """Link from the Tech Resources warranty PDF, kept separate from the
    numbered Instruction N columns per user decision."""
    instructions: list[str] = Field(default_factory=list)
    """Other Tech Resources PDF links (installation instructions etc.), in
    on-page order -> Instruction 1, Instruction 2, ..."""
    notes: list[str] = Field(default_factory=list)
    """Tech Resources warning/installation-notes text blocks (no link) ->
    Note 1, Note 2, ..."""

    auto: str | None = None
    """`{year||make||model,...}` - exact vehicle-application combos, same
    format as the AWE scraper's `auto` column."""
    submodel: str | None = None
    engine: str | None = None
    body_type: str | None = None
    transmission: str | None = None

    created_at: str | None = None
    updated_at: str | None = None
