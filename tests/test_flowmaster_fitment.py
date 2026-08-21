import pytest

from flowmaster.fitment import _format_auto, _format_grouped, fetch_fitment


def _opt(*values):
    return [{"value": v, "count": 1} for v in values]


class FakeClient:
    """Stands in for core.http_client.Client: maps the filter
    params of each producthelpers.php POST to a canned facet response, and
    records every call so the drill-down order/count can be asserted."""

    def __init__(self, responses: dict[tuple, dict]):
        self._responses = responses
        self.calls: list[dict] = []

    async def post_json(self, endpoint, data=None, headers=None):
        self.calls.append(dict(data))
        key = tuple(
            sorted((k, v) for k, v in data.items() if k not in ("action", "applicationType", "partnumber"))
        )
        options = self._responses.get(key, {})
        return {"data": {"vehicleApplications": {"options": options, "match": None}}}


@pytest.mark.asyncio
async def test_fetch_fitment_builds_exact_year_make_model_combos():
    # Mirrors the real site: Tahoe only exists under Chevrolet, Yukon only
    # under GMC, and 2021 has fewer years for Yukon than Tahoe - a naive
    # year x make x model cross product would be wrong here.
    responses = {
        (): {"make": _opt("Chevrolet", "GMC")},
        (("vehicleMake", "Chevrolet"),): {
            "model": _opt("Tahoe"),
            "submodel": _opt("RST", "N/A"),
            "engine": _opt("6.2L V8"),
            "body": [],
            "transmission": [],
        },
        (("vehicleMake", "GMC"),): {
            "model": _opt("Yukon"),
            "submodel": _opt("Denali"),
            "engine": _opt("6.2L V8"),
            "body": [],
            "transmission": [],
        },
        (("vehicleMake", "Chevrolet"), ("vehicleModel", "Tahoe")): {"year": _opt("2021", "2022")},
        (("vehicleMake", "GMC"), ("vehicleModel", "Yukon")): {"year": _opt("2022")},
    }
    client = FakeClient(responses)

    fitment = await fetch_fitment(client, "718216", "https://example.com/parts/718216")

    combos = fitment.auto[1:-1].split(",")
    assert set(combos) == {
        "2021||Chevrolet||Tahoe",
        "2022||Chevrolet||Tahoe",
        "2022||GMC||Yukon",
    }
    assert fitment.submodel == "Chevrolet: {RST}, GMC: {Denali}"  # N/A dropped
    assert fitment.engine == "Chevrolet: {6.2L V8}, GMC: {6.2L V8}"
    assert fitment.body_type is None
    assert fitment.transmission is None

    # 1 root call + 2 per-make calls + 2 per-(make,model) calls
    assert len(client.calls) == 5


@pytest.mark.asyncio
async def test_fetch_fitment_no_makes_returns_empty():
    client = FakeClient({(): {"make": []}})
    fitment = await fetch_fitment(client, "999999", "https://example.com/parts/999999")
    assert fitment.auto is None
    assert fitment.submodel is None
    assert len(client.calls) == 1  # stops after the root call, no per-make drill-down


def test_format_auto_empty_set_is_none():
    assert _format_auto(set()) is None


def test_format_auto_sorts_and_wraps():
    assert _format_auto({"2022||GMC||Yukon", "2021||Chevrolet||Tahoe"}) == (
        "{2021||Chevrolet||Tahoe,2022||GMC||Yukon}"
    )


def test_format_grouped_drops_empty_makes():
    assert _format_grouped({"Chevrolet": {"RST"}, "GMC": set()}) == "Chevrolet: {RST}"


def test_format_grouped_all_empty_is_none():
    assert _format_grouped({"Chevrolet": set()}) is None
