from awe_tuning_parsing.models import Image, Product, Variant
from awe_tuning_parsing.pipeline import _variant_images

_VARIANT_A = Variant(id=1, title="A", sku="3020-111", price=100.0, image_id=901)
_VARIANT_B = Variant(id=2, title="B", sku="3020-222", price=100.0, image_id=902)


def _product(images: list[Image], variants: list[Variant] | None = None) -> Product:
    return Product(
        id=1,
        title="Test Product",
        handle="test-product",
        url="https://example.com/products/test-product",
        variants=variants if variants is not None else [_VARIANT_A, _VARIANT_B],
        images=images,
    )


def test_variant_images_own_featured_image_first():
    images = [
        Image(id=901, src="https://cdn.example.com/a.jpg", variant_ids=[1]),
        Image(id=902, src="https://cdn.example.com/b.jpg", variant_ids=[2]),
    ]
    product = _product(images)

    assert _variant_images(product, _VARIANT_A) == ["https://cdn.example.com/a.jpg"]
    assert _variant_images(product, _VARIANT_B) == ["https://cdn.example.com/b.jpg"]


def test_variant_images_generic_untagged_photos_included_for_every_variant():
    images = [
        Image(id=900, src="https://cdn.example.com/generic1.jpg", variant_ids=[]),
        Image(id=901, src="https://cdn.example.com/a.jpg", variant_ids=[1]),
        Image(id=902, src="https://cdn.example.com/b.jpg", variant_ids=[2]),
        Image(id=903, src="https://cdn.example.com/generic2.jpg", variant_ids=[]),
    ]
    product = _product(images)

    images_a = _variant_images(product, _VARIANT_A)
    assert images_a[0] == "https://cdn.example.com/a.jpg"  # own featured image first
    assert "https://cdn.example.com/generic1.jpg" in images_a
    assert "https://cdn.example.com/generic2.jpg" in images_a
    assert "https://cdn.example.com/b.jpg" not in images_a  # tagged for the other variant only


def test_variant_images_tagged_for_multiple_variants_shown_to_both():
    images = [
        Image(id=901, src="https://cdn.example.com/a.jpg", variant_ids=[1]),
        Image(id=950, src="https://cdn.example.com/shared.jpg", variant_ids=[1, 2]),
        Image(id=902, src="https://cdn.example.com/b.jpg", variant_ids=[2]),
    ]
    product = _product(images)

    assert "https://cdn.example.com/shared.jpg" in _variant_images(product, _VARIANT_A)
    assert "https://cdn.example.com/shared.jpg" in _variant_images(product, _VARIANT_B)


def test_variant_images_no_featured_image_falls_back_to_first_product_image():
    variant = Variant(id=3, title="C", sku="3020-333", price=100.0, image_id=None)
    images = [
        Image(id=900, src="https://cdn.example.com/first.jpg", variant_ids=[]),
        Image(id=901, src="https://cdn.example.com/a.jpg", variant_ids=[1]),
    ]
    product = _product(images, variants=[variant])

    result = _variant_images(product, variant)
    assert result[0] == "https://cdn.example.com/first.jpg"


def test_variant_images_no_images_at_all():
    product = _product(images=[])
    assert _variant_images(product, _VARIANT_A) == []
