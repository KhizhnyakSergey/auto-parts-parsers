import json
from pathlib import Path

from awe_tuning_parsing.products import build_product

FIXTURES = Path(__file__).parent / "fixtures"


def test_build_product_from_raw_shopify_json():
    raw = json.loads((FIXTURES / "sample_product.json").read_text(encoding="utf-8"))
    product = build_product(raw)

    assert product.id == 123456789
    assert product.handle == "awe-track-edition-exhaust"
    assert product.url.endswith("/products/awe-track-edition-exhaust")

    assert len(product.variants) == 2
    assert product.price_min == 1399.00
    assert product.price_max == 1499.00
    assert product.in_stock is True  # first variant is available

    assert len(product.images) == 3
    assert product.images[1].id == 901
    assert product.images[1].variant_ids == [1]
    assert product.variants[0].image_id == 901  # variant 1's featured_image

    assert "304 stainless" in product.description
    assert "console.log" not in product.description  # <script> must be stripped

    # categories/vehicle_brands are filled in by the pipeline, not build_product
    assert product.categories == []
    assert product.vehicle_brands == []
