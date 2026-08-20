from awe_tuning_parsing.compatibility import FitmentRow, _parse_table, _strip_jsonp, build_variant_fitment

# Same table the user used to specify the grouping algorithm.
_ROWS = [
    FitmentRow("Audi", "A4 Quattro", "1997-2001", "Base", "1.8", "Sedan", "N/A", "SKU-A"),
    FitmentRow("Audi", "A4 Quattro", "1999-2000", "Avant", "1.8", "Wagon", "N/A", "SKU-A"),
    FitmentRow("Audi", "A4 Quattro", "2001", "Confort", "1.8", "Sedan", "N/A", "SKU-A"),
    FitmentRow("Audi", "A6 Quattro", "1998-1999", "Base", "2.8", "Sedan", "N/A", "SKU-A"),
    FitmentRow("Audi", "S4", "2000-2002", "Base", "2.7", "Sedan", "N/A", "SKU-A"),
    FitmentRow("Audi", "S4", "2001-2002", "Avant", "2.7", "Wagon", "N/A", "SKU-A"),
    FitmentRow("Volkswagen", "Passat", "1998-2001", "GLS", "1.8", "Sedan", "N/A", "SKU-A"),
    FitmentRow("Volkswagen", "Passat", "1998-2001", "GLS", "2.8", "Sedan", "N/A", "SKU-A"),
    FitmentRow("Volkswagen", "Passat", "1998-2001", "GLX", "2.8", "Sedan", "N/A", "SKU-A"),
    # A different SKU's row must never leak into SKU-A's columns.
    FitmentRow("Ford", "F-150", "2021", "Base", "5.0", "Truck", "6ft", "SKU-B"),
]


def test_auto_column_only_year_make_model():
    fitment = build_variant_fitment(_ROWS, "SKU-A")

    assert fitment.auto is not None
    assert fitment.auto.startswith("{") and fitment.auto.endswith("}")
    combos = fitment.auto[1:-1].split(",")
    assert "1997||Audi||A4 Quattro" in combos
    assert "2001||Audi||A4 Quattro" in combos  # range expanded
    assert "1999||Audi||A4 Quattro" in combos
    assert all("Submodel" not in c and "Sedan" not in c for c in combos)  # only 3 fields
    assert not any(c.startswith(("2021||Ford",)) for c in combos)  # other SKU excluded


def test_submodel_grouped_by_make():
    fitment = build_variant_fitment(_ROWS, "SKU-A")
    assert fitment.submodel == "Audi: {Avant, Base, Confort}, Volkswagen: {GLS, GLX}"


def test_engine_grouped_by_make():
    fitment = build_variant_fitment(_ROWS, "SKU-A")
    assert fitment.engine == "Audi: {1.8, 2.7, 2.8}, Volkswagen: {1.8, 2.8}"


def test_body_type_grouped_by_make():
    fitment = build_variant_fitment(_ROWS, "SKU-A")
    assert fitment.body_type == "Audi: {Sedan, Wagon}, Volkswagen: {Sedan}"


def test_bed_length_all_na_is_empty():
    fitment = build_variant_fitment(_ROWS, "SKU-A")
    assert fitment.bed_length is None


def test_bed_length_present_when_not_all_na():
    fitment = build_variant_fitment(_ROWS, "SKU-B")
    assert fitment.bed_length == "Ford: {6ft}"


def test_unknown_sku_returns_empty_fitment():
    fitment = build_variant_fitment(_ROWS, "does-not-exist")
    assert fitment.auto is None
    assert fitment.submodel is None
    assert fitment.html is None


_JSONP_RESPONSE = (
    'jQuery123456789_987654321({"html":'
    '"<h3>Compatible With<\\/h3><table class=\'ymm_table\'>'
    "<thead><tr><th class='field_2'>Make<\\/th><th class='field_3'>Model<\\/th>"
    "<th class='field_1'>Year<\\/th><th class='field_9'>SKU<\\/th><\\/tr><\\/thead>"
    "<tr><td>BMW<\\/td><td>330i<\\/td><td>2019<\\/td><td>3020-32429<\\/td><\\/tr>"
    '<\\/table>"});'
)


def test_strip_jsonp_extracts_inner_json():
    payload = _strip_jsonp(_JSONP_RESPONSE)
    assert payload is not None
    assert "<table" in payload["html"]


def test_parse_table_reads_headers_and_rows():
    payload = _strip_jsonp(_JSONP_RESPONSE)
    rows = _parse_table(payload["html"])
    assert len(rows) == 1
    assert rows[0].make == "BMW"
    assert rows[0].model == "330i"
    assert rows[0].year == "2019"
    assert rows[0].sku == "3020-32429"
