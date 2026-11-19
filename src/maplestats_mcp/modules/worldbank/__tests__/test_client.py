"""Tests for worldbank/client.py, shaped on live responses from 2026-10-03:
errors as HTTP 200 with a `message` body, null values for missing years,
newest-first rows, an ignored empty year range, topics with trailing spaces
or none at all, and 502 pages from the edge; and, from 2026-11-17, the
Data360 API's rows (see the last tests) that series data are read from first."""

from __future__ import annotations

import re

import pytest

from maplestats_mcp.modules.worldbank import client
from maplestats_mcp.shared import cache as cache_module
from maplestats_mcp.shared.errors import (
    InvalidInput,
    NotFound,
    UpstreamError,
    UpstreamUnavailable,
)

CATALOGUE = re.compile(r"https://api\.worldbank\.org/v2/(en|fr)/sources/2/indicators\?.*")
DATA = re.compile(r"https://api\.worldbank\.org/v2/(en|fr)/country/.*")
DATA360 = re.compile(r"https://data360api\.worldbank\.org/data360/data\?.*")

_ROWS = [
    {
        "id": "NY.GDP.MKTP.KD.ZG",
        "name": "GDP growth (annual %)",
        "unit": "",
        "sourceNote": "Annual percentage growth rate of GDP at market prices.",
        "sourceOrganization": "World Bank national accounts data",
        "topics": [{"id": "3", "value": "Economy & Growth"}],
    },
    {
        "id": "NY.GDP.MKTP.CD",
        "name": "GDP (current US$)",
        "unit": "",
        "sourceNote": "GDP at purchaser's prices.",
        "sourceOrganization": "World Bank national accounts data",
        "topics": [{"id": "3", "value": "Economy & Growth"}],
    },
    {
        "id": "SL.UEM.TOTL.ZS",
        "name": "Unemployment, total (% of total labor force) (modeled ILO estimate)",
        "unit": "",
        "sourceNote": "Share of the labor force without work.",
        "sourceOrganization": "ILO Modelled Estimates database (ILOEST)",
        "topics": [
            {"id": "4", "value": "Education "},
            {"id": "10", "value": "Social Protection & Labor"},
        ],
    },
    {
        "id": "XX.NO.TOPIC",
        "name": "Indicator without topic",
        "unit": "",
        "sourceNote": "",
        "sourceOrganization": "",
        "topics": [],
    },
]


def _catalogue(rows=_ROWS):
    return [{"page": 1, "pages": 1, "per_page": "2000", "total": len(rows)}, rows]


def _row(iso, name, year, value, code="NY.GDP.MKTP.KD.ZG"):
    return {
        "indicator": {"id": code, "value": "GDP growth (annual %)"},
        "country": {"id": iso[:2], "value": name},
        "countryiso3code": iso,
        "date": str(year),
        "value": value,
        "unit": "",
        "obs_status": "",
        "decimal": 1,
    }


def _data(rows):
    header = {"page": 1, "pages": 1, "per_page": 5000, "total": len(rows)}
    header |= {"sourceid": "2", "lastupdated": "2026-07-13"}
    return [header, rows]


def _data360_down(httpx_mock):
    """Series data are read from Data360 first; these tests are about the v2 endpoint."""
    httpx_mock.add_response(
        url=DATA360, status_code=503, text="unavailable", is_reusable=True, is_optional=True
    )


@pytest.fixture(autouse=True)
def _reset_cache():
    cache_module._caches.clear()
    yield


async def test_search_requires_every_word_and_ranks_name_hits(httpx_mock):
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    result = await client.search_indicators("GDP growth")
    assert [i.id for i in result.indicators] == ["NY.GDP.MKTP.KD.ZG"]
    assert result.provenance.licence and "CC BY 4.0" in result.provenance.licence


async def test_catalogue_reads_every_page(httpx_mock):
    first, second = _ROWS[:1], _ROWS[1:]
    meta = {"pages": 2, "per_page": "2000", "total": len(_ROWS)}
    httpx_mock.add_response(url=CATALOGUE, json=[{"page": 1, **meta}, first])
    httpx_mock.add_response(url=CATALOGUE, json=[{"page": 2, **meta}, second])
    rows, _ = await client._catalogue("en")
    assert len(rows) == len(_ROWS)
    assert httpx_mock.get_requests()[1].url.params["page"] == "2"


async def test_catalogue_short_of_its_total_is_an_error(httpx_mock):
    meta = {"page": 1, "pages": 1, "per_page": "2000", "total": len(_ROWS) + 5}
    httpx_mock.add_response(url=CATALOGUE, json=[meta, _ROWS])
    with pytest.raises(UpstreamError, match=f"read {len(_ROWS)} of {len(_ROWS) + 5} indicators"):
        await client._catalogue("en")


async def test_search_by_code_and_topic_name_with_trailing_space(httpx_mock):
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    by_code = await client.search_indicators("sl.uem.totl.zs")
    assert by_code.indicators[0].id == "SL.UEM.TOTL.ZS"
    by_topic = await client.search_indicators(topic="education")
    assert by_topic.topic == "Education"
    assert [i.id for i in by_topic.indicators] == ["SL.UEM.TOTL.ZS"]


async def test_list_topics_counts_and_skips_empty(httpx_mock):
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    topics = await client.list_topics()
    assert [t.id for t in topics.topics] == ["3", "4", "10"]
    assert topics.topics[0].name == "Economy & Growth (2)"


async def test_unknown_topic_and_empty_search_are_invalid(httpx_mock):
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    with pytest.raises(InvalidInput):
        await client.search_indicators()
    with pytest.raises(InvalidInput, match="Unknown WDI topic"):
        await client.search_indicators(topic="zzz")


async def test_french_search_provenance_and_errors(httpx_mock):
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    result = await client.search_indicators("GDP growth", lang="fr")
    assert (result.provenance.freshness or "").endswith("par année ; les valeurs sont annuelles.")
    assert "indicateurs) ; chaque mot" in (result.provenance.coverage or "")
    assert (result.provenance.licence or "").startswith("Source : Banque mondiale")
    assert (
        "reproduce_code" in result.provenance.reproduce and "appelez" in result.provenance.reproduce
    )
    with pytest.raises(InvalidInput, match="^Entrée invalide : thème WDI inconnu"):
        await client.search_indicators(topic="zzz", lang="fr")
    with pytest.raises(NotFound, match="n'est pas un code des Indicateurs"):
        await client.get_indicator("NOPE.X", lang="fr")
    with pytest.raises(InvalidInput, match="pas les deux"):
        await client.get_canada_series(
            "NY.GDP.MKTP.KD.ZG", start_year=2000, most_recent=3, lang="fr"
        )


async def test_get_indicator_not_in_wdi_is_not_found(httpx_mock):
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    detail = await client.get_indicator("SL.UEM.TOTL.ZS")
    assert detail.source_organization.startswith("ILO")
    assert detail.topics == ["Education", "Social Protection & Labor"]
    with pytest.raises(NotFound):
        await client.get_indicator("NOPE.X")


async def test_series_sorts_drops_nulls_and_ranks(httpx_mock):
    _data360_down(httpx_mock)
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    httpx_mock.add_response(
        url=DATA,
        json=_data(
            [
                _row("CAN", "Canada", 2025, 1.7),
                _row("CAN", "Canada", 2024, 2.0),
                _row("CAN", "Canada", 2023, None),
                _row("USA", "United States", 2024, 2.8),
                _row("USA", "United States", 2025, None),
                _row("DEU", "Germany", 2024, -0.2),
                _row("OED", "OECD members", 2024, 1.8),
            ]
        ),
    )
    result = await client.get_canada_series(
        "ny.gdp.mktp.kd.zg", compare_with=["usa", "DEU", "OECD"]
    )
    request = httpx_mock.get_requests()[-1]
    assert "/country/CAN;USA;DEU;OED/indicator/NY.GDP.MKTP.KD.ZG" in str(request.url)
    canada = result.countries[0]
    assert [o.year for o in canada.observations] == [2024, 2025]
    assert canada.latest_year == 2025
    # 2025 has only Canada, so the rank uses 2024, which three countries report.
    assert (result.canada_rank, result.rank_year, result.ranked_countries) == (2, 2024, 3)
    assert any("OECD members" in n for n in result.notes)


async def test_empty_year_range_is_filtered_here(httpx_mock):
    """The API ignores date=2030:2100 and sends every year."""
    _data360_down(httpx_mock)
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    httpx_mock.add_response(url=DATA, json=_data([_row("CAN", "Canada", 2024, 2.0)]))
    with pytest.raises(NotFound, match="no value for Canada"):
        await client.get_canada_series("NY.GDP.MKTP.KD.ZG", start_year=2030)


async def test_api_message_body_becomes_invalid_input(httpx_mock):
    _data360_down(httpx_mock)
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    httpx_mock.add_response(
        url=DATA,
        json=[{"message": [{"id": "120", "key": "Invalid value", "value": "not valid"}]}],
    )
    with pytest.raises(InvalidInput, match="not valid"):
        await client.get_canada_series("NY.GDP.MKTP.KD.ZG")


async def test_comparisons_outside_g7_oecd_are_refused():
    with pytest.raises(InvalidInput, match="OECD"):
        await client.get_canada_series("NY.GDP.MKTP.KD.ZG", compare_with=["CHN"])
    with pytest.raises(InvalidInput):
        await client.get_canada_series("NY.GDP.MKTP.KD.ZG", start_year=2000, most_recent=3)


async def test_g7_alias_expands_without_duplicating_canada(httpx_mock):
    _data360_down(httpx_mock)
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    httpx_mock.add_response(url=DATA, json=_data([_row("CAN", "Canada", 2024, 2.0)]))
    result = await client.get_canada_series("NY.GDP.MKTP.KD.ZG", compare_with=["G7", "USA"])
    assert "/country/CAN;USA;GBR;FRA;DEU;ITA;JPN/" in str(httpx_mock.get_requests()[-1].url)
    assert any("No values for" in n for n in result.notes)


async def test_most_recent_keeps_last_years(httpx_mock):
    _data360_down(httpx_mock)
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    rows = [_row("CAN", "Canada", y, float(y - 2000)) for y in range(2025, 2015, -1)]
    httpx_mock.add_response(url=DATA, json=_data(rows))
    result = await client.get_canada_series("NY.GDP.MKTP.KD.ZG", most_recent=3)
    assert [o.year for o in result.countries[0].observations] == [2023, 2024, 2025]


async def test_502_edge_page_is_unavailable(httpx_mock):
    _data360_down(httpx_mock)
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    for _ in range(3):
        httpx_mock.add_response(url=DATA, status_code=502, text="<html>Bad gateway</html>")
    with pytest.raises(UpstreamUnavailable):
        await client.get_canada_series("NY.GDP.MKTP.KD.ZG")


def _d360(ref_area, year, value, indicator="WB_WDI_NY_GDP_MKTP_KD_ZG", **extra):
    return {
        "OBS_VALUE": None if value is None else str(value),
        "TIME_FORMAT": "P1Y",
        "UNIT_MULT": 0,
        "OBS_STATUS": "A",
        "DATABASE_ID": "WB_WDI",
        "INDICATOR": indicator,
        "REF_AREA": ref_area,
        "SEX": "_T",
        "AGE": "_T",
        "URBANISATION": "_T",
        "TIME_PERIOD": str(year),
        "FREQ": "A",
        "UNIT_MEASURE": "PC_A",
        **extra,
    }


def _d360_answer(rows, count=None):
    return {"count": len(rows) if count is None else count, "value": rows}


async def test_series_come_from_data360_first_with_names_and_no_v2_call(httpx_mock):
    # Rows as the API sent them on 2026-11-17: strings for values, codes without names.
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    httpx_mock.add_response(
        url=DATA360,
        json=_d360_answer(
            [
                _d360("CAN", 2024, 2.0),
                _d360("CAN", 2020, -5.038233),
                _d360("CAN", 2023, None),
                _d360("USA", 2024, 2.8),
                _d360("OED", 2024, 1.8),
            ]
        ),
    )
    result = await client.get_canada_series(
        "ny.gdp.mktp.kd.zg", compare_with=["USA", "OECD"], start_year=2020, end_year=2024
    )
    request = httpx_mock.get_requests()[-1]
    params = request.url.params
    assert request.url.host == "data360api.worldbank.org"
    assert params["DATABASE_ID"] == "WB_WDI"
    assert params["INDICATOR"] == "WB_WDI_NY_GDP_MKTP_KD_ZG"
    assert params["REF_AREA"] == "CAN,USA,OED"
    assert (params["timePeriodFrom"], params["timePeriodTo"], params["top"]) == (
        "2020",
        "2024",
        "1000",
    )
    assert not [r for r in httpx_mock.get_requests() if r.url.host == "api.worldbank.org"][1:]
    canada = result.countries[0]
    assert (canada.country_name, [o.year for o in canada.observations]) == ("Canada", [2020, 2024])
    assert canada.observations[0].value == pytest.approx(-5.038233)
    assert result.countries[2].country_name == "OECD members"
    assert result.provenance.url.startswith("https://data360api.worldbank.org/data360/data")
    assert "Data360" in (result.provenance.coverage or "")
    assert (result.canada_rank, result.rank_year) == (2, 2024)


async def test_data360_french_gets_french_country_names(httpx_mock):
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    httpx_mock.add_response(
        url=DATA360, json=_d360_answer([_d360("CAN", 2024, 2.0), _d360("USA", 2024, 2.8)])
    )
    result = await client.get_canada_series("NY.GDP.MKTP.KD.ZG", compare_with=["USA"], lang="fr")
    assert [c.country_name for c in result.countries] == ["Canada", "États-Unis"]
    assert "Lu dans l'API Data360" in (result.provenance.coverage or "")


async def test_v2_is_the_fallback_when_data360_does_not_answer(httpx_mock):
    """2026-11-17: the v2 data call hung; here it is Data360 that fails and v2 that answers."""
    _data360_down(httpx_mock)
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    httpx_mock.add_response(url=DATA, json=_data([_row("CAN", "Canada", 2024, 2.0)]))
    result = await client.get_canada_series("NY.GDP.MKTP.KD.ZG")
    assert result.countries[0].latest_value == 2.0
    assert result.provenance.url.startswith("https://api.worldbank.org/v2/")
    assert "Indicators API v2" in (result.provenance.coverage or "")
    assert "2026-07-13" in (result.provenance.freshness or "")


async def test_v2_is_the_fallback_when_data360_has_no_row_for_canada(httpx_mock):
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    httpx_mock.add_response(url=DATA360, json=_d360_answer([]))
    httpx_mock.add_response(url=DATA, json=_data([_row("CAN", "Canada", 2024, 2.0)]))
    result = await client.get_canada_series("NY.GDP.MKTP.KD.ZG")
    assert result.provenance.url.startswith("https://api.worldbank.org/v2/")


async def test_v2_is_the_fallback_for_breakdown_rows(httpx_mock):
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    # Two rows for Canada in 2024 (a breakdown by sex): which is WDI's own cannot be told.
    httpx_mock.add_response(
        url=DATA360,
        json=_d360_answer([_d360("CAN", 2024, 2.0), _d360("CAN", 2024, 3.0, SEX="F")]),
    )
    httpx_mock.add_response(url=DATA, json=_data([_row("CAN", "Canada", 2024, 2.0)]))
    result = await client.get_canada_series("NY.GDP.MKTP.KD.ZG")
    assert result.provenance.url.startswith("https://api.worldbank.org/v2/")
    assert result.countries[0].latest_value == 2.0


async def test_v2_is_the_fallback_for_an_unknown_data360_shape(httpx_mock):
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    httpx_mock.add_response(url=DATA360, json={"message": "nothing"})
    httpx_mock.add_response(url=DATA, json=_data([_row("CAN", "Canada", 2023, 1.0)]))
    result = await client.get_canada_series("NY.GDP.MKTP.KD.ZG")
    assert result.countries[0].latest_year == 2023


async def test_data360_pages_through_a_series_with_skip(httpx_mock):
    """2026-11-17: a call returns 1,000 rows however many match (`count` says how many
    do); a series cut at the first page ended Canada's population at 2021."""
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    # Rows come in no useful order: Canada has 5 on the first page and 20 on the second.
    first = [_d360("USA", 1500 + i, 1.0) for i in range(995)]
    first += [_d360("CAN", 1995 + i, float(i)) for i in range(5)]
    second = [_d360("CAN", 2000 + i, float(i)) for i in range(20)]
    second += [_d360("USA", 3000 + i, 1.0) for i in range(5)]
    httpx_mock.add_response(url=DATA360, json=_d360_answer(first, count=1025))
    httpx_mock.add_response(url=DATA360, json=_d360_answer(second, count=1025))
    result = await client.get_canada_series("NY.GDP.MKTP.KD.ZG", compare_with=["USA"])
    requests = [r for r in httpx_mock.get_requests() if r.url.host == "data360api.worldbank.org"]
    assert [r.url.params.get("skip") for r in requests] == [None, "1000"]
    # Canada's rows come from both pages.
    assert len(result.countries[0].observations) == 25
    assert result.countries[1].country_code == "USA"
    assert result.provenance.url.startswith("https://data360api.worldbank.org/")


async def test_a_series_with_more_rows_than_the_cap_goes_to_v2(httpx_mock):
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    httpx_mock.add_response(url=DATA360, json=_d360_answer([_d360("CAN", 2024, 1.0)], count=5001))
    httpx_mock.add_response(url=DATA, json=_data([_row("CAN", "Canada", 2024, 2.0)]))
    result = await client.get_canada_series("NY.GDP.MKTP.KD.ZG")
    assert result.provenance.url.startswith("https://api.worldbank.org/v2/")
    assert (
        len([r for r in httpx_mock.get_requests() if r.url.host == "data360api.worldbank.org"]) == 1
    )


async def test_a_short_data360_page_is_not_passed_off_as_whole(httpx_mock):
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    httpx_mock.add_response(url=DATA360, json=_d360_answer([_d360("CAN", 2024, 1.0)], count=3))
    httpx_mock.add_response(url=DATA, json=_data([_row("CAN", "Canada", 2024, 2.0)]))
    result = await client.get_canada_series("NY.GDP.MKTP.KD.ZG")
    assert result.provenance.url.startswith("https://api.worldbank.org/v2/")


async def test_both_apis_down_is_unavailable(httpx_mock):
    _data360_down(httpx_mock)
    httpx_mock.add_response(url=CATALOGUE, json=_catalogue())
    httpx_mock.add_response(
        url=DATA, status_code=502, text="<html>Bad gateway</html>", is_reusable=True
    )
    with pytest.raises(UpstreamUnavailable, match="did not answer"):
        await client.get_canada_series("NY.GDP.MKTP.KD.ZG")
