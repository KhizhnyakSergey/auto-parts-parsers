"""Data model for a scraped Shopify product, plus the category it was discovered under."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Category(BaseModel):
    """A node from the site's header navigation (`header__inline-menu`)."""

    label: str
    handle: str
    """Collection handle, e.g. 'audi' for /collections/audi."""
    group: str
    """Top-level nav bucket this category came from, e.g. 'Vehicles' or 'Exhausts'."""
    kind: str
    """'vehicle' for brand collections under Vehicles, 'product_type' for the rest."""


class Variant(BaseModel):
    id: int
    title: str
    sku: str = ""
    price: float
    compare_at_price: float | None = None
    available: bool = True
    image_id: int | None = None
    """Shopify's `variants[].featured_image.id` - this variant's main photo."""


class Image(BaseModel):
    id: int
    src: str
    alt: str | None = None
    variant_ids: list[int] = Field(default_factory=list)
    """Variants this photo is tagged for. Empty means it's generic/shared -
    Shopify shows it for every variant, not just one."""


class Product(BaseModel):
    id: int
    title: str
    handle: str
    vendor: str = ""
    product_type: str = ""
    tags: list[str] = Field(default_factory=list)
    url: str

    description: str = ""
    """Plain-text description extracted from body_html via selectolax."""

    categories: list[str] = Field(default_factory=list)
    """Category labels (from the header nav) this product was found under."""
    vehicle_brands: list[str] = Field(default_factory=list)
    """Subset of categories that are vehicle-brand collections, e.g. 'Audi', 'BMW'."""

    price_min: float | None = None
    price_max: float | None = None
    currency: str = "USD"
    in_stock: bool = False

    variants: list[Variant] = Field(default_factory=list)
    images: list[Image] = Field(default_factory=list)

    created_at: str | None = None
    updated_at: str | None = None


class ProductRow(BaseModel):
    """One exploded variant of a product - the unit that becomes one Excel row.

    Product-level fields (categories, tabs, description, ...) are duplicated
    across every variant row of the same product; only price/sku/images/title
    and the fitment columns are variant-specific.
    """

    product_id: int
    variant_id: int
    title: str
    sku: str
    url: str
    vendor: str = ""
    product_type: str = ""
    categories: list[str] = Field(default_factory=list)
    vehicle_brands: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    price: float | None = None
    compare_at_price: float | None = None
    currency: str = "USD"
    in_stock: bool = True
    images: list[str] = Field(default_factory=list)
    """Photo URLs for this variant, in display order - images[0] is the main photo."""

    description: str = ""
    """Plain-text description from the Shopify JSON body_html."""
    details_text: str = ""
    """Formatted text of the on-page `.productView-details` description block."""
    important_fitment_notes: str = ""

    tabs: dict[str, str] = Field(default_factory=dict)
    """Tab title (as shown on-site) -> raw HTML content, e.g. "Performance Specs"."""
    instruction_links: list[str] = Field(default_factory=list)
    """Links from the "Installation Instructions" tab, in on-page order."""
    video_links: list[str] = Field(default_factory=list)
    """Links from the "SEE IT IN ACTION" video gallery, in on-page order."""

    auto: str | None = None
    """`{year||make||model,...}` compatibility combos for this variant's SKU."""
    submodel: str | None = None
    engine: str | None = None
    body_type: str | None = None
    bed_length: str | None = None
    variant_fits_html: str | None = None
    """Raw HTML fitment table (variant-fits__content), filtered to this SKU."""

    created_at: str | None = None
    updated_at: str | None = None
