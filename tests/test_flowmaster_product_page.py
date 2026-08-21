from flowmaster.product_page import parse_product_page

_PRODUCT_DATA = """
{
  "partnumber": "718216",
  "name": "Flowmaster Flow FX Cat-Back Exhaust System",
  "brand": "Flowmaster",
  "price": 1499.85,
  "quantity": 15,
  "lifecycleStatus": "active",
  "created": "2024-05-23 14:37:37",
  "lastmodified": "2026-08-20 03:10:48",
  "categories": [
    {"navnamehierarchy": "All Exhaust/Exhaust Series/Flow FX", "defaultcategory": "true"},
    {"navnamehierarchy": "All Exhaust/Exhaust Systems/Cat-Back", "defaultcategory": "false"}
  ],
  "videos": {
    "abc123": {"type": "general", "source": "youtube", "mediainformation": "abc123"}
  }
}
"""

_PAGE_TEMPLATE = """
<html><body>
<script id="product_data" type="application/json">{product_data}</script>

<div class="breadcrumbs"><ul>
<li><a href="/"><span>Home</span></a><span> / </span></li>
<li><a href="/products/exhaust/" title="All Exhaust"><span class="breadcrumb">All Exhaust</span></a><span> / </span></li>
<li><span><strong class="breadcrumb">Flowmaster Flow FX Cat-Back Exhaust System</strong></span></li>
</ul></div>

<h1 class="product-name">Flowmaster Flow FX Cat-Back Exhaust System</h1>
<div class="short-description">
  <p class="show-less">21-26 Tahoe, Yukon, Yukon XL, Suburban 6.2L Flow FX Cat-Back Dual Exit (DOR)</p>
  <span class="read-more">Read More</span>
</div>
<div class="product-stock-status"><p class="in-stock">In Stock</p></div>

<div class="product-gallery">
  <div class="product-image-carousel">
    <div class="carousel-item" data-fresco-index="1">
      <div class="product_thumbnail" style="background-image:url('//images.flowmastermufflers.com/583x/second.jpg')"></div>
    </div>
    <div class="carousel-item" data-fresco-index="0">
      <div class="product_thumbnail" style="background-image:url('//images.flowmastermufflers.com/583x/first.jpg')"></div>
    </div>
  </div>
</div>

<div class="price  short-margin">
  <div class="webprice main-price" data-price="1499.85">$1,499.85</div>
</div>

<span id="partnumber" data-partnumber="718216">&nbsp;718216</span>

<button type="button" class="collapsible"><div class="collapsible-title">Overview</div></button>
<div class="row-contents"><div class="full_description">Great exhaust sound.</div></div>

<button type="button" class="collapsible"><div class="collapsible-title">Specs</div></button>
<div class="row-contents">
  <table class="attributes-table"><tbody>
    <tr><th class="label">Brand</th><td class="data">Flowmaster</td></tr>
    <tr><th class="label">Body Material</th><td class="data">409 Stainless Steel</td></tr>
  </tbody></table>
</div>

<button type="button" class="collapsible"><div class="collapsible-title">Emissions</div></button>
<div class="row-contents"><div class="emission-code ec5"><span>5</span></div><br>Legal for sale everywhere.</div>

<button type="button" class="collapsible"><div class="collapsible-title">Tech Resources</div></button>
<div class="row-contents">
  <div class="widget_info tech_resource_links">
    <a href="//documents.flowmastermufflers.com/warranty.pdf" title="Warranty - Flowmaster Warranty 26 Update.pdf">
      <div class="widget_text">Warranty - Flowmaster Warranty 26 Update.pdf</div>
    </a>
  </div>
  <div class="widget_info tech_resource_links">
    <a href="//documents.flowmastermufflers.com/install.pdf" title="Instructions - 718216_Installation Instructions.pdf">
      <div class="widget_text">Instructions - 718216_Installation Instructions.pdf</div>
    </a>
  </div>
  <div class="widget_info">
    <div class="widget_text installation_notes product_info">Fits 21-26 GM SUVs with 6.2L engine.</div>
  </div>
</div>

<button type="button" class="collapsible"><div class="collapsible-title">Vehicle Applications</div></button>
<div class="row-contents"><div id="vehicle-applications" class="applications product_info"></div></div>
</body></html>
"""

_URL = "https://www.flowmastermufflers.com/products/exhaust/exhaust_series/flowfx/parts/718216"


def _parse():
    html = _PAGE_TEMPLATE.format(product_data=_PRODUCT_DATA)
    return parse_product_page(html, _URL)


def test_basic_fields():
    row = _parse()
    assert row.sku == "718216"
    assert row.title == "Flowmaster Flow FX Cat-Back Exhaust System"
    assert row.url == _URL
    assert row.brand == "Flowmaster"
    assert row.lifecycle_status == "active"
    assert row.quantity == 15
    assert row.in_stock is True


def test_breadcrumbs_join_on_link_text_not_separator():
    row = _parse()
    assert row.breadcrumbs == "Home / All Exhaust / Flowmaster Flow FX Cat-Back Exhaust System"


def test_short_description_excludes_read_more():
    row = _parse()
    assert row.short_description == "21-26 Tahoe, Yukon, Yukon XL, Suburban 6.2L Flow FX Cat-Back Dual Exit (DOR)"
    assert "Read More" not in row.short_description


def test_stock_status_text():
    row = _parse()
    assert row.stock_status == "In Stock"


def test_price_prefers_html_data_attribute():
    row = _parse()
    assert row.price == 1499.85


def test_gallery_images_ordered_by_fresco_index():
    row = _parse()
    assert row.images == [
        "https://images.flowmastermufflers.com/583x/first.jpg",
        "https://images.flowmastermufflers.com/583x/second.jpg",
    ]


def test_videos_from_product_data_json():
    row = _parse()
    assert row.videos == ["https://www.youtube.com/watch?v=abc123"]


def test_overview_html_from_full_description():
    row = _parse()
    assert "Great exhaust sound." in row.overview_html


def test_specs_table_becomes_label_value_dict():
    row = _parse()
    assert row.specs == {"Brand": "Flowmaster", "Body Material": "409 Stainless Steel"}


def test_emissions_text():
    row = _parse()
    assert "Legal for sale everywhere." in row.emissions


def test_tech_resources_split_warranty_instructions_notes():
    row = _parse()
    assert row.instruction_warranty == "https://documents.flowmastermufflers.com/warranty.pdf"
    assert row.instructions == ["https://documents.flowmastermufflers.com/install.pdf"]
    assert row.notes == ["Fits 21-26 GM SUVs with 6.2L engine."]


def test_categories_from_product_data():
    row = _parse()
    assert row.categories == [
        "All Exhaust/Exhaust Series/Flow FX",
        "All Exhaust/Exhaust Systems/Cat-Back",
    ]


def test_discontinued_product_falls_back_to_brand_and_sku_title():
    product_data = """
    {"partnumber": "817437", "name": "", "brand": "Flowmaster", "price": 240.74,
     "quantity": 0, "lifecycleStatus": "obsolete"}
    """
    html = """
    <html><body>
    <script id="product_data" type="application/json">{data}</script>
    <h1 class="product-name"></h1>
    <div class="product-stock-status"><p>Not Available</p></div>
    <span id="partnumber" data-partnumber="817437"></span>
    </body></html>
    """.format(data=product_data)

    row = parse_product_page(html, "https://www.flowmastermufflers.com/products/discontinued/parts/817437")
    assert row.title == "Flowmaster 817437"
    assert row.in_stock is False
    assert row.lifecycle_status == "obsolete"
