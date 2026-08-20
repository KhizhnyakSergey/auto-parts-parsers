from awe_tuning_parsing.product_page import parse_product_page

_PAGE_TEMPLATE = """
<html><body>
<div id="custom-product-tabs"><header class="header-tabs"></header><div class="body-tabs"></div></div>
<script>
 const data =  {{
    "tabs": [
      {{
        "title": "Description",
        "content": "<p>Great exhaust.</p>"
      }},
      {{
        "title": "Installation Instructions",
        "content": "<p><a href=\\"https://cdn.example.com/install.pdf\\">Install PDF</a></p><div><a href=\\"https://awe-tuning.com/pages/prop65\\">Prop 65</a></div>"
      }},
    ]
  }};
</script>

<div class="halo-productView-right productView-details clearfix">
  <div class="productView-moreItem"><h1>Some Product Title</h1></div>
  <div class="productView-moreItem"><p>Great intro text.</p><p><span><strong>Important Fitment Notes:</strong><br>This exhaust is <strong>confirmed</strong> to fit the RS6 GT.</span></p></div>
  <style>.u-select{{color:red}}</style>
  <div class="product_filters"><select><option>should not leak into text</option></select></div>
</div>

<div class="video-tab-gallery__container container">
  <div class="video-tab-gallery__swipers-wrapper">
    <div class="video-tab-gallery__swiper-container" data-product-videos="">
      <div class="swiper-wrapper">
        <figure class="video-tab-gallery__slide">
          <a href="https://youtu.be/aaaa1111" class="video-tab-gallery__venobox-trigger venobox" data-vbtype="video"></a>
        </figure>
        <figure class="video-tab-gallery__slide">
          <a href="https://youtu.be/bbbb2222" class="video-tab-gallery__venobox-trigger venobox" data-vbtype="video"></a>
        </figure>
      </div>
    </div>
    <div class="video-tab-gallery__swiper-container" data-customer-videos="">
      <div class="swiper-wrapper">
        <figure class="video-tab-gallery__slide">
          <a href="https://youtu.be/cccc3333" class="video-tab-gallery__venobox-trigger venobox" data-vbtype="video"></a>
        </figure>
      </div>
    </div>
  </div>
</div>

{variants}
</body></html>
"""

_VARIANT_SECTION = """
<section class="product-variants__variant" id="var-111">
  <div class="product-variants__variant-title">
    <h1 class="product-variant__title">Track Edition - Chrome</h1>
    <p class="product-variant__sku" data-sku="3020-111">(SKU: 3020-111)</p>
  </div>
  <div class="product-variants__variant-price">
    <span class="compare-price">$836.84</span>
    <span class="price on-sale">$795.00</span>
  </div>
</section>
<section class="product-variants__variant" id="var-222">
  <div class="product-variants__variant-title">
    <h1 class="product-variant__title">Track Edition - Black</h1>
    <p class="product-variant__sku" data-sku="3020-222">(SKU: 3020-222)</p>
  </div>
  <div class="product-variants__variant-price">
    <span class="price">$795.00</span>
  </div>
</section>
"""


def test_parse_product_page_tabs_and_instructions():
    html = _PAGE_TEMPLATE.format(variants="")
    data = parse_product_page(html)

    assert data.tabs == {"Description": "<p>Great exhaust.</p>"}
    assert data.instruction_links == ["https://cdn.example.com/install.pdf"]  # prop65 link filtered out


def test_parse_product_page_details_and_fitment_notes():
    html = _PAGE_TEMPLATE.format(variants="")
    data = parse_product_page(html)

    assert "Great intro text." in data.details_text
    assert "should not leak into text" not in data.details_text  # filter widget excluded
    assert "color:red" not in data.details_text  # style stripped
    assert data.fitment_notes.startswith("Important Fitment Notes:")
    assert "This exhaust is confirmed to fit the RS6 GT." in data.fitment_notes


def test_parse_product_page_variants():
    html = _PAGE_TEMPLATE.format(variants=_VARIANT_SECTION)
    data = parse_product_page(html)

    assert set(data.variants.keys()) == {111, 222}
    v = data.variants[111]
    assert v.title == "Track Edition - Chrome"
    assert v.sku == "3020-111"
    assert v.price == 795.00
    assert v.compare_at_price == 836.84

    v2 = data.variants[222]
    assert v2.compare_at_price is None


def test_parse_product_page_no_variants_section():
    html = _PAGE_TEMPLATE.format(variants="")
    data = parse_product_page(html)
    assert data.variants == {}


def test_parse_product_page_video_links():
    html = _PAGE_TEMPLATE.format(variants="")
    data = parse_product_page(html)

    # product videos and customer videos combined, in on-page order
    assert data.video_links == [
        "https://youtu.be/aaaa1111",
        "https://youtu.be/bbbb2222",
        "https://youtu.be/cccc3333",
    ]


def test_parse_product_page_no_video_gallery():
    html = "<html><body><p>No videos here</p></body></html>"
    data = parse_product_page(html)
    assert data.video_links == []
