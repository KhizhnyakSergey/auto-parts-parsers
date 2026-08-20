from pathlib import Path

from awe_tuning_parsing.categories import parse_categories

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_categories_from_header_menu():
    html = (FIXTURES / "home_page.html").read_text(encoding="utf-8")
    categories = parse_categories(html)

    handles = {c.handle for c in categories}
    assert "audi" in handles
    assert "bmw" in handles
    assert "exhaust" in handles
    assert "intakes" in handles

    audi = next(c for c in categories if c.handle == "audi")
    assert audi.kind == "vehicle"
    assert audi.group == "Vehicles"

    exhaust = next(c for c in categories if c.handle == "exhaust")
    assert exhaust.kind == "product_type"

    # info-only nav entries (About Us, AWE Life) must not leak in as categories
    assert "company" not in handles
    assert "news" not in handles
