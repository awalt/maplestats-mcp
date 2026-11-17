"""Indicators the feed gives no level for (issue #272).

Confirmed live 2026-11-16 in the raw ind-all.json: the Consumer Price Index comes with
`"value": {"en": "", "fr": ""}` and only `growth` ("3.1%", 12-month change). The empty
text is upstream, so `value` stays an empty string (a nullable field would break
clients) and `provenance.limits` names the indicators and says where the level is."""

from __future__ import annotations

import pytest

from maplestats_mcp.modules.statcan.indicators import client, constants
from maplestats_mcp.shared import cache as cache_module


@pytest.fixture(autouse=True)
def _clear_cache():
    cache_module._caches.clear()
    yield
    cache_module._caches.clear()


_GEO = [
    {"geo_code": "0", "label": {"en": "Canada", "fr": "Canada"}},
    {"geo_code": "9", "label": {"en": "Alberta", "fr": "Alberta"}},
]


def _indicator(
    registry: int,
    number: int,
    title: str,
    value: str = "",
    *,
    geo_code: int = 0,
    fr_title: str | None = None,
    fr_value: str | None = None,
    source: str = "18100004",
) -> dict:
    return {
        "registry_number": registry,
        "indicator_number": number,
        "geo_code": geo_code,
        "title": {"en": title, "fr": fr_title or title},
        "value": {"en": value, "fr": value if fr_value is None else fr_value},
        "refper": {"en": "October 2026", "fr": "Octobre 2026"},
        "source": source,
        "release_date": "2026-11-16",
        "growth_rate": {
            "growth": {"en": "3.1%", "fr": "3,1 %"},
            "details": {"en": "(12-month change)", "fr": "(variation sur 12 mois)"},
        },
    }


# The Consumer Price Index as the live feed sends it (ids and fields from ind-all.json).
_CPI = _indicator(3665, 1, "Consumer Price Index", fr_title="Indice des prix à la consommation")
_SHELTER = _indicator(3665, 3, "Shelter", fr_title="Logement")
_UNEMPLOYMENT = _indicator(
    2, 1, "Unemployment rate", "6.9%", fr_title="Taux de chômage", fr_value="6,9 %"
)


def _feed(*indicators: dict) -> dict:
    return {"results": {"geo": _GEO, "indicators": list(indicators)}}


async def test_an_empty_value_is_named_with_where_to_find_the_level(httpx_mock):
    httpx_mock.add_response(url=constants.DATASET_URLS["all"], json=_feed(_CPI, _UNEMPLOYMENT))
    result = await client.get_indicators(query="consumer price index")
    cpi = result.indicators[0]
    # The output keeps its shape: an empty string, not None, and growth is still there.
    assert cpi.value == ""
    assert cpi.growth == "3.1%"
    limits = result.provenance.limits or ""
    assert "Consumer Price Index" in limits
    assert "growth" in limits and "growth_details" in limits
    assert "wds_get_data_from_vectors" in limits
    assert "v41690973 is the all-items CPI for Canada" in limits


async def test_only_indicators_without_a_value_are_named(httpx_mock):
    httpx_mock.add_response(url=constants.DATASET_URLS["all"], json=_feed(_CPI, _UNEMPLOYMENT))
    result = await client.get_indicators()
    assert [item.value for item in result.indicators] == ["", "6.9%"]
    limits = result.provenance.limits or ""
    assert "Consumer Price Index" in limits
    assert "Unemployment rate" not in limits


async def test_no_note_when_every_indicator_has_a_value(httpx_mock):
    httpx_mock.add_response(url=constants.DATASET_URLS["all"], json=_feed(_UNEMPLOYMENT))
    result = await client.get_indicators()
    assert result.provenance.limits is None


async def test_an_indicator_beyond_the_page_is_not_named(httpx_mock):
    """The note is about the indicators of this result, not of the whole feed."""
    httpx_mock.add_response(url=constants.DATASET_URLS["all"], json=_feed(_UNEMPLOYMENT, _CPI))
    result = await client.get_indicators(limit=1)
    assert [item.title for item in result.indicators] == ["Unemployment rate"]
    assert result.provenance.limits is None


async def test_a_missing_value_key_counts_as_empty(httpx_mock):
    without_value = _indicator(3665, 3, "Shelter")
    del without_value["value"]
    httpx_mock.add_response(url=constants.DATASET_URLS["all"], json=_feed(without_value))
    result = await client.get_indicators()
    assert result.indicators[0].value == ""
    assert "Shelter" in (result.provenance.limits or "")


async def test_no_vector_is_named_for_an_indicator_it_was_not_checked_against(httpx_mock):
    httpx_mock.add_response(url=constants.DATASET_URLS["all"], json=_feed(_SHELTER))
    result = await client.get_indicators()
    limits = result.provenance.limits or ""
    assert "Shelter" in limits
    assert "source_table" in limits and "wds_get_data_from_cube_coord" in limits
    assert "v41690973" not in limits


async def test_a_provincial_cpi_does_not_get_the_canada_vector(httpx_mock):
    alberta = _indicator(3665, 1, "Consumer Price Index", geo_code=9)
    httpx_mock.add_response(url=constants.DATASET_URLS["all"], json=_feed(alberta))
    result = await client.get_indicators()
    assert "v41690973" not in (result.provenance.limits or "")


async def test_a_title_repeated_for_several_places_is_named_once(httpx_mock):
    housing = [
        _indicator(3605, 1, "New Housing Price Index", geo_code=code, source="18100205")
        for code in (0, 9)
    ]
    httpx_mock.add_response(url=constants.DATASET_URLS["all"], json=_feed(*housing))
    result = await client.get_indicators()
    assert result.returned_count == 2
    assert (result.provenance.limits or "").count("New Housing Price Index") == 1


async def test_many_titles_are_capped_and_the_rest_counted(httpx_mock):
    many = constants.EMPTY_VALUE_TITLES_MAX + 3
    rows = [_indicator(100 + n, 1, f"Index number {n}") for n in range(many)]
    httpx_mock.add_response(url=constants.DATASET_URLS["all"], json=_feed(*rows))
    result = await client.get_indicators()
    limits = result.provenance.limits or ""
    assert "Index number 0" in limits
    assert f"Index number {constants.EMPTY_VALUE_TITLES_MAX}" not in limits
    assert "and 3 more" in limits


async def test_the_note_joins_the_other_notes_of_the_call(httpx_mock):
    httpx_mock.add_response(url=constants.DATASET_URLS["all"], json=_feed(_CPI))
    result = await client.get_indicators(limit=constants.SEARCH_LIMIT_MAX + 1)
    limits = result.provenance.limits or ""
    assert "lowered to the maximum" in limits
    assert "Consumer Price Index" in limits


async def test_the_note_is_in_french_for_a_french_call(httpx_mock):
    httpx_mock.add_response(url=constants.DATASET_URLS["all"], json=_feed(_CPI))
    result = await client.get_indicators(lang="fr")
    assert result.indicators[0].value == ""
    limits = result.provenance.limits or ""
    assert "Indice des prix à la consommation" in limits
    assert "le fil ne donne pas de niveau" in limits
    assert "v41690973 est l'IPC d'ensemble du Canada" in limits
    assert "In this result" not in limits
