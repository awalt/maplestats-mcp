"""Tests for ilo/client.py on responses recorded live on 2026-11-08
(fixtures/): the dataflow list in English and French (8 of its 1,215 flows),
the structure of DF_UNE_DEAP_SEX_AGE_RT (area codelist and constraint cut to
ten codes) and SDMX-CSV data in English (annual, four areas) and French
(monthly). The 404 text and the HTTP 500 Oracle error are the API's own."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

import pytest

from maplestats_mcp.modules.ilo import client
from maplestats_mcp.shared.errors import InvalidInput, NotFound, UpstreamError

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _sdmx_is_up(monkeypatch):
    """The SDMX cooldown is module state: start every test with it clear."""
    monkeypatch.setattr(client, "_sdmx_down_until", 0.0)


CATALOGUE = "https://sdmx.ilo.org/rest/dataflow/ILO/all/latest"
STRUCTURE = re.compile(
    r"https://sdmx\.ilo\.org/rest/dataflow/ILO/DF_UNE_DEAP_SEX_AGE_RT/latest\?.*"
)
DATA = re.compile(r"https://sdmx\.ilo\.org/rest/data/ILO,DF_UNE_DEAP_SEX_AGE_RT,/.*")


def _json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _mock(httpx_mock, csv_name: str | None = "data_une_en.csv", lang: str = "en"):
    httpx_mock.add_response(
        url=CATALOGUE,
        json=_json(f"dataflows_{lang}.json"),
        is_optional=True,
        is_reusable=True,
    )
    httpx_mock.add_response(
        url=STRUCTURE, json=_json("structure_une.json"), is_optional=True, is_reusable=True
    )
    if csv_name:
        httpx_mock.add_response(url=DATA, text=_text(csv_name))


def _data_requests(httpx_mock):
    return [r for r in httpx_mock.get_requests() if "/rest/data/" in str(r.url)]


# ------------------------------------------------------------------ search


async def test_search_ranks_name_matches_and_flags_modelled(httpx_mock):
    httpx_mock.add_response(url=CATALOGUE, json=_json("dataflows_en.json"))
    result = await client.search_datasets("unemployment rate")
    ids = [d.id for d in result.datasets]
    assert ids[0] == "DF_UNE_DEAP_SEX_AGE_RT"
    modelled = next(d for d in result.datasets if d.id == "DF_UNE_2EAP_SEX_AGE_RT")
    assert modelled.modelled is True
    assert result.datasets[0].modelled is False
    # HTML is gone and LAST_UPDATE (dd/mm/yyyy) is read as ISO.
    assert "<" not in result.datasets[0].description
    assert result.datasets[0].last_updated and result.datasets[0].last_updated.startswith("2026-")
    assert result.provenance.commercial_use == "allowed"
    assert "CC BY 4.0" in (result.provenance.licence or "")


async def test_search_in_french_folds_accents(httpx_mock):
    httpx_mock.add_response(
        url=CATALOGUE, json=_json("dataflows_fr.json"), match_headers={"Accept-Language": "fr"}
    )
    result = await client.search_datasets("chomage par sexe et age", lang="fr")
    assert result.datasets[0].id == "DF_UNE_DEAP_SEX_AGE_RT"
    assert "chômage" in result.datasets[0].name.lower()


async def test_search_needs_words():
    with pytest.raises(InvalidInput, match="words"):
        await client.search_datasets("the of")


# --------------------------------------------------------------- structure


async def test_describe_gives_codes_with_data_and_a_canada_key(httpx_mock):
    _mock(httpx_mock, csv_name=None)
    result = await client.describe_dataset("ILO,DF_UNE_DEAP_SEX_AGE_RT")
    assert result.key_template == "REF_AREA.FREQ.MEASURE.SEX.AGE"
    assert result.example_key == "CAN..UNE_DEAP_RT.."
    area = result.dimensions[0]
    assert {"CAN", "USA", "X01"} <= {c.id for c in area.codes}
    sex = next(d for d in result.dimensions if d.id == "SEX")
    assert ("SEX_T", "Total") in [(c.id, c.name) for c in sex.codes]
    assert "lastNObservations=1" in result.csv_url and "csvfilewithlabels" in result.csv_url
    assert result.citation.startswith("International Labour Organization (")


async def test_unknown_dataset_is_not_found(httpx_mock):
    _mock(httpx_mock, csv_name=None)
    with pytest.raises(NotFound, match="ilo_search_datasets"):
        await client.describe_dataset("DF_NOPE")


async def test_bad_dataset_id_is_invalid():
    with pytest.raises(InvalidInput):
        await client.describe_dataset("unemployment")


# --------------------------------------------------------------------- data


async def test_get_data_parses_rows_units_sources_and_status(httpx_mock):
    _mock(httpx_mock)
    result = await client.get_data(
        "DF_UNE_DEAP_SEX_AGE_RT", "can+usa+gbr+x01.a.une_deap_rt.sex_t.age_ythadult_yge15", last_n=3
    )
    # Codes are normalised to the API's case before the request.
    assert result.key == "CAN+USA+GBR+X01.A.UNE_DEAP_RT.SEX_T.AGE_YTHADULT_YGE15"
    request = _data_requests(httpx_mock)[0]
    assert request.url.params["lastNObservations"] == "3"
    canada = next(s for s in result.series if s.ref_area == "CAN")
    assert canada.source == "LFS - Labour Force Survey"
    assert canada.unit == "Percentage" and canada.frequency == "Annual"
    rows = [r for r in result.rows if r.ref_area == "CAN"]
    assert [r.period for r in rows] == sorted(r.period for r in rows)
    assert any(r.period == "2025" and abs(r.value - 6.819) < 1e-9 for r in rows)
    usa = [r for r in result.rows if r.ref_area == "USA"]
    assert any(r.status == "Break in series" for r in usa)
    assert any("harmonises national survey figures" in n for n in result.notes)


def _une_with_gaps() -> str:
    """The annual answer with values missing the way SDMX-CSV writes them (an empty
    OBS_VALUE and an OBS_STATUS): Canada 2024, and all of the United Kingdom."""
    rows = list(csv.reader(io.StringIO(_text("data_une_en.csv"))))
    header, body = rows[0], rows[1:]
    area, period = (
        header.index("REF_AREA: Reference area"),
        header.index("TIME_PERIOD: Time period"),
    )
    value, status = header.index("OBS_VALUE"), header.index("OBS_STATUS: Observation status")
    for row in body:
        if row[area].startswith("GBR") or (row[area].startswith("CAN") and row[period] == "2024"):
            row[value], row[status] = "", "M: Missing value"
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(rows)
    return out.getvalue()


async def test_get_data_says_how_many_values_were_left_out_and_why(httpx_mock):
    _mock(httpx_mock, csv_name=None)
    httpx_mock.add_response(url=DATA, text=_une_with_gaps())
    result = await client.get_data(
        "DF_UNE_DEAP_SEX_AGE_RT", "can+usa+gbr+x01.a.une_deap_rt.sex_t.age_ythadult_yge15", last_n=3
    )
    # The rows are as before: no 2024 for Canada, and no United Kingdom series.
    assert [r.period for r in result.rows if r.ref_area == "CAN"] == ["2023", "2025"]
    assert "GBR" not in {s.ref_area for s in result.series}
    sentence = next(n for n in result.notes if "no numeric value" in n)
    assert "4 observations had no numeric value" in sentence and "4 Missing value" in sentence
    assert "1 series had no numeric value at all" in sentence
    assert sentence in (result.provenance.limits or "")


async def test_get_data_says_it_in_french_too(httpx_mock):
    _mock(httpx_mock, csv_name=None, lang="fr")
    httpx_mock.add_response(url=DATA, text=_une_with_gaps())
    result = await client.get_data(
        "DF_UNE_DEAP_SEX_AGE_RT",
        "can+usa+gbr+x01.a.une_deap_rt.sex_t.age_ythadult_yge15",
        last_n=3,
        lang="fr",
    )
    sentence = next(n for n in result.notes if "sans valeur numérique" in n)
    assert "4 Missing value" in sentence and "aucune valeur numérique" in sentence
    assert sentence in (result.provenance.limits or "")


async def test_get_data_without_gaps_has_no_such_note(httpx_mock):
    _mock(httpx_mock)
    result = await client.get_data(
        "DF_UNE_DEAP_SEX_AGE_RT", "can+usa+gbr+x01.a.une_deap_rt.sex_t.age_ythadult_yge15", last_n=3
    )
    assert not any("no numeric value" in n for n in result.notes)


async def test_compare_says_how_many_values_were_left_out_and_why(httpx_mock):
    _mock(httpx_mock, csv_name=None)
    httpx_mock.add_response(url=DATA, text=_une_with_gaps())
    result = await client.compare_countries("unemployment_rate", compare_with=["US", "uk", "world"])
    assert any("4 observations had no numeric value" in n for n in result.notes)


async def test_get_data_in_french_reads_monthly_periods(httpx_mock):
    _mock(httpx_mock, csv_name="data_une_fr.csv", lang="fr")
    result = await client.get_data(
        "DF_UNE_DEAP_SEX_AGE_RT", "CAN.M.UNE_DEAP_RT.SEX_T.AGE_YTHADULT_YGE15", last_n=3, lang="fr"
    )
    assert all(r.period.startswith("2026-M") for r in result.rows)
    assert result.series[0].frequency == "Mensuel"
    assert result.series[0].unit == "Pourcentage"
    assert result.citation.startswith("Organisation internationale du Travail")


async def test_unknown_area_fails_before_a_request(httpx_mock):
    # ILOSTAT answers an unknown area with HTTP 500 (ORA-00936).
    _mock(httpx_mock, csv_name=None)
    with pytest.raises(InvalidInput, match="ZZZ is not a REF_AREA code"):
        await client.get_data(
            "DF_UNE_DEAP_SEX_AGE_RT", "ZZZ.A.UNE_DEAP_RT.SEX_T.AGE_YTHADULT_YGE15"
        )
    assert not _data_requests(httpx_mock)


async def test_short_key_is_explained(httpx_mock):
    _mock(httpx_mock, csv_name=None)
    with pytest.raises(InvalidInput, match="5 parts in the order REF_AREA.FREQ.MEASURE.SEX.AGE"):
        await client.get_data("DF_UNE_DEAP_SEX_AGE_RT", "CAN.A")


async def test_open_key_without_periods_is_refused(httpx_mock):
    _mock(httpx_mock, csv_name=None)
    with pytest.raises(InvalidInput, match="last_n or start_period"):
        await client.get_data("DF_UNE_DEAP_SEX_AGE_RT", "...SEX_T.")


async def test_no_data_404_is_not_found(httpx_mock):
    _mock(httpx_mock, csv_name=None)
    httpx_mock.add_response(
        url=DATA,
        status_code=404,
        text="No data is found. Please adjust your query parameters and try again.",
    )
    with pytest.raises(NotFound, match="in the periods asked for"):
        await client.get_data(
            "DF_UNE_DEAP_SEX_AGE_RT",
            "CAN.A.UNE_DEAP_RT.SEX_T.AGE_YTHADULT_YGE15",
            start_period="2040",
        )


async def test_server_error_is_an_upstream_error(httpx_mock):
    _mock(httpx_mock, csv_name=None)
    httpx_mock.add_response(url=DATA, status_code=500, text="ORA-00936: missing expression")
    with pytest.raises(UpstreamError, match="HTTP 500"):
        await client.get_data(
            "DF_UNE_DEAP_SEX_AGE_RT", "CAN.A.UNE_DEAP_RT.SEX_T.AGE_YTHADULT_YGE15"
        )


async def test_bad_period_is_invalid():
    with pytest.raises(InvalidInput, match="SDMX period"):
        await client.get_data("DF_UNE_DEAP_SEX_AGE_RT", "CAN.A...", start_period="last year")


# --------------------------------------------------------------- comparison


async def test_compare_puts_canada_first_and_ranks_countries_only(httpx_mock):
    _mock(httpx_mock)
    result = await client.compare_countries(
        "unemployment_rate", compare_with=["US", "uk", "world", "XYZ"]
    )
    request = _data_requests(httpx_mock)[0]
    assert "/CAN+USA+GBR+X01.A.UNE_DEAP_RT.SEX_T.AGE_YTHADULT_YGE15" in str(request.url)
    assert request.url.params["lastNObservations"] == "10"
    assert [c.area_code for c in result.countries] == ["CAN", "USA", "GBR", "X01"]
    # X01 (World) is shown but not ranked; Canada's 6.8 is above the US and UK.
    assert result.canada_rank == 1 and result.ranked_countries == 3
    assert result.rank_period == "2025"
    assert any("XYZ" in n for n in result.notes)
    assert any("status" in n for n in result.notes)
    assert result.frequency == "annual" and result.sex == "total"


async def test_compare_checks_frequency_and_sex():
    with pytest.raises(InvalidInput, match="frequencies: annual"):
        await client.compare_countries("labour_income_share", frequency="monthly")
    with pytest.raises(InvalidInput, match="no breakdown by sex"):
        await client.compare_countries("minimum_wage_ppp", sex="female")
    with pytest.raises(InvalidInput, match="Unknown indicator"):
        await client.compare_countries("gdp")
    with pytest.raises(InvalidInput, match="not an ILOSTAT area code"):
        await client.compare_countries("unemployment_rate", compare_with=["United-States-of-A"])


ACCESS_DENIED = (
    "<!DOCTYPE html><html><head><title>403 - Forbidden: Access is denied.</title></head>"
    "<body><h2>403 - Forbidden: Access is denied.</h2></body></html>"
)


async def test_access_denied_page_is_unavailable_and_describe_falls_back(httpx_mock):
    # 2026-11-08: the full dataflow list answered this 403 page now and then, from
    # three networks, while one dataflow's own definition still answered.
    from maplestats_mcp.shared.errors import UpstreamUnavailable

    httpx_mock.add_response(url=CATALOGUE, status_code=403, text=ACCESS_DENIED, is_reusable=True)
    httpx_mock.add_response(
        url="https://sdmx.ilo.org/rest/dataflow/ILO/DF_UNE_DEAP_SEX_AGE_RT/latest",
        json=_json("structure_une.json"),
    )
    httpx_mock.add_response(url=STRUCTURE, json=_json("structure_une.json"), is_reusable=True)
    with pytest.raises(UpstreamUnavailable):
        await client.search_datasets("unemployment")
    result = await client.describe_dataset("DF_UNE_DEAP_SEX_AGE_RT")
    assert result.key_template == "REF_AREA.FREQ.MEASURE.SEX.AGE"


# ------------------------------------------------------------ rplumber route
# sdmx.ilo.org answered the IIS access-denied page to every request on 2026-11-17
# while rplumber.ilo.org served the same ILOSTAT tables. rplumber_une_m.csv is
# that answer as recorded (Canada, monthly, 2026M01 to 2026M09); rplumber_une_a.csv
# is synthetic: the real columns, with United States values made up for the test.

RPLUMBER = re.compile(r"https://rplumber\.ilo\.org/data/indicator/\?.*")
SDMX_FLOW = "https://sdmx.ilo.org/rest/dataflow/ILO/DF_UNE_DEAP_SEX_AGE_RT/latest"


def _sdmx_denied(httpx_mock):
    for url in (CATALOGUE, SDMX_FLOW, STRUCTURE, DATA):
        httpx_mock.add_response(
            url=url, status_code=403, text=ACCESS_DENIED, is_reusable=True, is_optional=True
        )


def _rplumber_requests(httpx_mock):
    return [r for r in httpx_mock.get_requests() if r.url.host == "rplumber.ilo.org"]


async def test_compare_reads_rplumber_when_sdmx_is_denied(httpx_mock):
    _sdmx_denied(httpx_mock)
    httpx_mock.add_response(url=RPLUMBER, text=_text("rplumber_une_m.csv"))
    result = await client.compare_countries("unemployment_rate", frequency="monthly", last_n=3)
    request = _rplumber_requests(httpx_mock)[0]
    # The `+` between codes is sent as written, as the API documents it, never as %2B.
    query = request.url.query.decode()
    assert "id=UNE_DEAP_SEX_AGE_RT_M" in query and "sex=SEX_T" in query
    assert "classif1=AGE_YTHADULT_YGE15" in query and "type=both" in query
    assert "timefrom=" in query and "ref_area=CAN" in query
    canada = result.countries[0]
    assert canada.area_code == "CAN" and canada.area_name == "Canada"
    # Newest three months, oldest first, in SDMX period spelling.
    assert [o.period for o in canada.observations] == ["2026-M07", "2026-M08", "2026-M09"]
    assert canada.latest_period == "2026-M09" and canada.latest_value == pytest.approx(6.189)
    assert canada.source == "LFS - Labour Force Survey" and canada.unit == "Percentage"
    assert result.dataset == "DF_UNE_DEAP_SEX_AGE_RT"
    assert result.csv_url.startswith("https://rplumber.ilo.org/data/indicator/")
    assert result.provenance.url.startswith("https://rplumber.ilo.org/")
    assert any("rplumber" in n for n in result.notes)
    assert "rplumber" in (result.provenance.coverage or "")


async def test_compare_joins_codes_with_a_plain_plus_and_ranks(httpx_mock):
    _sdmx_denied(httpx_mock)
    httpx_mock.add_response(url=RPLUMBER, text=_text("rplumber_une_a.csv"))
    result = await client.compare_countries("unemployment_rate", compare_with=["US", "GBR"])
    assert "ref_area=CAN+USA+GBR" in _rplumber_requests(httpx_mock)[0].url.query.decode()
    assert [c.area_code for c in result.countries] == ["CAN", "USA"]
    assert result.canada_rank == 1 and result.ranked_countries == 2
    assert result.rank_period == "2025"
    usa = result.countries[1]
    assert any(o.status == "Break in series" for o in usa.observations)
    # GBR has no rows in the answer: said, not hidden.
    assert any("GBR" in n for n in result.notes)
    assert any("status" in n for n in result.notes)


async def test_compare_in_french_asks_for_french_labels(httpx_mock):
    _sdmx_denied(httpx_mock)
    httpx_mock.add_response(url=RPLUMBER, text=_text("rplumber_une_a.csv"))
    result = await client.compare_countries("unemployment_rate", lang="fr")
    assert "lang=fr" in _rplumber_requests(httpx_mock)[0].url.query.decode()
    assert any("L'API SDMX d'ILOSTAT" in n for n in result.notes)


async def test_second_compare_skips_sdmx_during_the_cooldown(httpx_mock):
    _sdmx_denied(httpx_mock)
    httpx_mock.add_response(url=RPLUMBER, text=_text("rplumber_une_a.csv"), is_reusable=True)
    await client.compare_countries("unemployment_rate")
    sdmx_before = len([r for r in httpx_mock.get_requests() if r.url.host == "sdmx.ilo.org"])
    assert sdmx_before >= 1
    await client.compare_countries("unemployment_rate", compare_with=["USA"])
    sdmx_after = len([r for r in httpx_mock.get_requests() if r.url.host == "sdmx.ilo.org"])
    assert sdmx_after == sdmx_before


async def test_get_data_reads_a_preset_dataset_from_rplumber(httpx_mock):
    _sdmx_denied(httpx_mock)
    httpx_mock.add_response(url=RPLUMBER, text=_text("rplumber_une_a.csv"))
    result = await client.get_data(
        "DF_UNE_DEAP_SEX_AGE_RT",
        "can+usa.a.une_deap_rt.sex_t.age_ythadult_yge15",
        last_n=2,
    )
    assert result.key == "CAN+USA.A.UNE_DEAP_RT.SEX_T.AGE_YTHADULT_YGE15"
    canada = next(s for s in result.series if s.ref_area == "CAN")
    assert canada.key == "CAN.A.UNE_DEAP_RT.SEX_T.AGE_YTHADULT_YGE15"
    assert canada.frequency == "Annual" and canada.observation_count == 2
    rows = [r for r in result.rows if r.ref_area == "CAN"]
    assert [(r.period, r.value) for r in rows] == [("2024", 6.4), ("2025", 6.819)]
    assert result.dataset_name == "Unemployment rate by sex and age (%)"
    assert any("rplumber" in n for n in result.notes)
    assert result.csv_url.startswith("https://rplumber.ilo.org/")


async def test_rplumber_counts_last_n_back_from_a_past_end_period(httpx_mock):
    # last_n=10 with end_period=2015 asked rplumber for timefrom = this year - 13,
    # so the window held 2013 to 2015 and the call returned three years, not ten.
    _sdmx_denied(httpx_mock)
    header, *_ = _text("rplumber_une_a.csv").splitlines()
    canada = _text("rplumber_une_a.csv").splitlines()[3]
    rows = [
        canada.replace('"2025",6.819', f'"{year}",{year - 2000}.5') for year in range(2002, 2016)
    ]
    httpx_mock.add_response(url=RPLUMBER, text="\n".join([header, *rows]))
    result = await client.get_data(
        "DF_UNE_DEAP_SEX_AGE_RT",
        "can.a.une_deap_rt.sex_t.age_ythadult_yge15",
        end_period="2015",
        last_n=10,
    )
    query = _rplumber_requests(httpx_mock)[0].url.query.decode()
    assert "timefrom=2002" in query and "timeto=2015" in query
    assert [r.period for r in result.rows] == [str(year) for year in range(2006, 2016)]


def test_rplumber_from_year_counts_back_from_the_end_period():
    from maplestats_mcp.modules.ilo import rplumber

    assert rplumber.from_year(None, 10, "A", 2026, "2015") == 2002
    assert rplumber.from_year(None, 24, "M", 2026, "2015-M06") == 2010
    # An end period in the future cannot hold data: count back from this year.
    assert rplumber.from_year(None, 10, "A", 2026, "2030") == 2013
    # A start period still wins.
    assert rplumber.from_year("2008", 10, "A", 2026, "2015") == 2008


async def test_get_data_rplumber_checks_the_key_before_a_request(httpx_mock):
    _sdmx_denied(httpx_mock)
    with pytest.raises(InvalidInput, match="5 parts in the order REF_AREA.FREQ.MEASURE.SEX.AGE"):
        await client.get_data("DF_UNE_DEAP_SEX_AGE_RT", "CAN.A")
    with pytest.raises(InvalidInput, match="one frequency"):
        await client.get_data("DF_UNE_DEAP_SEX_AGE_RT", "CAN..UNE_DEAP_RT.SEX_T.AGE_YTHADULT_YGE15")
    with pytest.raises(InvalidInput, match="holds the measure UNE_DEAP_RT"):
        await client.get_data(
            "DF_UNE_DEAP_SEX_AGE_RT", "CAN.A.EMP_DEAP_RT.SEX_T.AGE_YTHADULT_YGE15"
        )
    with pytest.raises(InvalidInput, match="last_n or start_period"):
        await client.get_data("DF_UNE_DEAP_SEX_AGE_RT", ".A.UNE_DEAP_RT.SEX_T.")
    assert not _rplumber_requests(httpx_mock)


async def test_get_data_for_another_dataset_stays_unavailable(httpx_mock):
    from maplestats_mcp.shared.errors import UpstreamUnavailable

    httpx_mock.add_response(url=CATALOGUE, status_code=403, text=ACCESS_DENIED, is_reusable=True)
    httpx_mock.add_response(
        url="https://sdmx.ilo.org/rest/dataflow/ILO/DF_EMP_TEMP_SEX_AGE_NB/latest",
        status_code=403,
        text=ACCESS_DENIED,
    )
    with pytest.raises(UpstreamUnavailable, match="rplumber"):
        await client.get_data(
            "DF_EMP_TEMP_SEX_AGE_NB", "CAN.A.EMP_TEMP_NB.SEX_T.AGE_AGGREGATE_TOTAL"
        )
    assert not _rplumber_requests(httpx_mock)


async def test_rplumber_failure_is_unavailable(httpx_mock):
    from maplestats_mcp.shared.errors import UpstreamUnavailable

    _sdmx_denied(httpx_mock)
    httpx_mock.add_response(url=RPLUMBER, status_code=503, text="Service Unavailable")
    with pytest.raises(UpstreamUnavailable, match="rplumber API answered HTTP 503"):
        await client.compare_countries("unemployment_rate")


async def test_rplumber_without_canada_is_not_found(httpx_mock):
    _sdmx_denied(httpx_mock)
    header = _text("rplumber_une_a.csv").splitlines()[0]
    httpx_mock.add_response(url=RPLUMBER, text=header + "\n")
    with pytest.raises(NotFound, match="no unemployment_rate values for Canada"):
        await client.compare_countries("unemployment_rate")


def test_rplumber_helpers():
    from maplestats_mcp.modules.ilo import rplumber

    assert rplumber.sdmx_period("2026M09") == "2026-M09"
    assert rplumber.sdmx_period("2025Q4") == "2025-Q4"
    assert rplumber.sdmx_period("2025") == "2025"
    assert rplumber.sdmx_period("last year") is None
    assert rplumber.indicator_id("DF_UNE_DEAP_SEX_AGE_RT", "M") == "UNE_DEAP_SEX_AGE_RT_M"
    # 24 monthly values need two years and a margin; a start period wins; none means all years.
    assert rplumber.from_year(None, 24, "M", 2026) == 2021
    assert rplumber.from_year("2020-03", 24, "M", 2026) == 2020
    assert rplumber.from_year(None, None, "A", 2026) is None
    found = rplumber.shape_for("DF_EAR_INEE_CUR_NB")
    assert found is not None
    shape, modelled = found
    assert shape.kinds == ("area", "freq", "measure", "classif1")
    assert shape.classif1 == "CUR_TYPE_PPP" and modelled is False
    modelled_flow = rplumber.shape_for("DF_LAP_2GDP_NOC_RT")
    assert modelled_flow is not None and modelled_flow[1] is True
    assert rplumber.shape_for("DF_EMP_TEMP_SEX_AGE_NB") is None
