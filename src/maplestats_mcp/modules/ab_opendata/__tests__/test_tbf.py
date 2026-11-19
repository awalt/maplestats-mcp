"""Treasury Board and Finance tools, against workbooks laid out as seen live on 2026-11-19.

The workbooks are built here with the live layouts: the Activity Index sheet
"AAX" with its header in row 1 over a blank date column; the projections'
title rows above Year, Gender, Total and ages 0 to 100, notes under the table,
genders "Women +", "Men +" and "All"; the summary's footnote digits glued to
its headers and the two dependency ratios under one header.
"""

from __future__ import annotations

import io
import re
from datetime import datetime

import pytest
from openpyxl import Workbook

from maplestats_mcp.modules.ab_opendata import client, constants
from maplestats_mcp.shared import cache as cache_module
from maplestats_mcp.shared.errors import InvalidInput, NotFound, UpstreamError

AAX_DATASET = "fd4d584a-305e-432e-b2e8-60b11cc47973"
AAX_RESOURCE = "ad4cb55d-4df3-4455-a6dc-71ce010a79b2"
AAX_URL = (
    f"https://open.alberta.ca/dataset/{AAX_DATASET}/resource/{AAX_RESOURCE}"
    "/download/alberta-activity-index-data-tables.xlsx"
)
PROJ_DATASET = "0a312cd4-2d3f-49b2-8f94-edb19a70742e"
FILES = {
    "all": ("33a5f834-f3e0-4664-bdea-92cbdeb0f6b4", "all assumptions (low, medium and high)"),
    "summary": ("a35c1477-dc38-4508-8e90-568c9f0c7717", "summary - medium growth assumption"),
    "cd": ("32865a90-f69f-4b76-928a-2698169f4973", "census divisions (CDs)"),
    "alga": ("78bff0c2-9970-45d6-94cd-535563418a26", "aggregated local geographic areas (ALGAs)"),
    "lga": ("27356952-4ac4-4d2e-9ba5-0808ef548768", "local geographic areas (LGAs)"),
}


def _url(key: str) -> str:
    return (
        f"https://open.alberta.ca/dataset/{PROJ_DATASET}/resource/{FILES[key][0]}"
        f"/download/tbf-{key}.xlsx"
    )


def _bytes(book: Workbook) -> bytes:
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _aax_book() -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "AAX"
    sheet.append([None, "Alberta Activity Index (January 1981 = 100)"])
    for index in range(30):
        year, month = 1981 + index // 12, index % 12 + 1
        sheet.append([datetime(year, month, 1), 100.00000000000004 + index])
    return _bytes(book)


def _projection_sheet(book: Workbook, title: str, base: int, area: str | None = None) -> None:
    sheet = book.create_sheet(title)
    sheet.append([f"Alberta Population Projections (2026-2051), {title}"])
    if area is not None:
        sheet.append([area])
    sheet.append([])
    sheet.append(["Year", "Gender", "Total", *range(101)])
    for year in (2001, 2025, 2026, 2051):
        for gender, share in (("Women +", 0.5), ("Men +", 0.5), ("All", 1.0)):
            total = int((base + year) * share)
            sheet.append([year, gender, total, *[total // 101] * 101])
    sheet.append(["Sources: Treasury Board and Finance, Statistics Canada."])
    sheet.append(["Notes:"])
    sheet.append(["1. Population as of July 1."])


def _scenario_book() -> bytes:
    book = Workbook()
    book.remove(book.active)  # type: ignore[arg-type]
    for title, base in (("Low Scenario", 1000), ("Med Scenario", 2000), ("High Scenario", 3000)):
        _projection_sheet(book, title, base)
    return _bytes(book)


def _areas_book(areas: list[str]) -> bytes:
    book = Workbook()
    book.remove(book.active)  # type: ignore[arg-type]
    for number, area in enumerate(areas):
        _projection_sheet(book, area, 100 * (number + 1), area)
    return _bytes(book)


def _summary_book(drop_births: bool = False) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "Alberta"
    header = [
        "Year",
        "Population July 11 2 3",
        "Percent Change in Population",
        "Ratio of Men+ to Women+4",
        "Average Age5",
        "Dependency Ratios6",
        None,
        "Period (July to June)",
        "Total Fertility Rate7",
        "Median Age at Death8",
        "Births",
        "Deaths",
        "Immigrants",
        "Net Emigrants9",
        "Net NPR10",
        "Net Interprovincial",
        "Total Net Migration",
    ]
    if drop_births:
        header[10] = "Something else"
    sheet.append(["Summary Statistics, Medium Scenario, Alberta"])
    sheet.append([])
    sheet.append(header)
    sheet.append([None, None, None, None, None, "Child", "Elderly"])
    sheet.append([2001, 3058554, 1.8, 102, 35.4, 29.6, 14.6, "2000-01", ".", ".", 37202])
    sheet.append(
        [2051, 6959145, 1.2, 100, 43.4, 23.9, 32.9, "2050-51", 1.6, 85.1, 73000, 53285]
        + [58800, 9900, 2500, 13000, 74400]
    )
    sheet.append(["Sources: Treasury Board and Finance (Projections: 2026-2051)."])
    return _bytes(book)


def _resource(rid: str, name: str, url: str) -> dict:
    return {"id": rid, "name": name, "format": "XLSX", "url": url, "size": 1000}


def _package(name: str, dataset_id: str, resources: list[dict]) -> dict:
    return {
        "success": True,
        "result": {
            "id": dataset_id,
            "name": name,
            "title": name,
            "type": "opendata",
            "license_id": "OGLA",
            "license_title": "Open Government Licence - Alberta",
            "updatefrequency": "Monthly",
            "organization": {"name": "treasuryboardandfinance", "title": "TBF"},
            "resources": resources,
        },
    }


def _projection_package(edition: int = 2026) -> dict:
    resources = [
        _resource(
            rid,
            f"Alberta population projections {edition}-2051 - {words}",
            _url(key),
        )
        for key, (rid, words) in FILES.items()
    ]
    return _package(f"alberta-population-projections-{edition}-2051", PROJ_DATASET, resources)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache_module._caches.clear()
    yield


@pytest.fixture
def aax(httpx_mock):
    resources = [_resource(AAX_RESOURCE, "Monthly Alberta Activity Index data table", AAX_URL)]
    httpx_mock.add_response(
        url=re.compile(rf".*package_show\?id=(alberta-activity-index-data-tables|{AAX_DATASET})$"),
        json=_package(constants.ACTIVITY_INDEX_DATASET, AAX_DATASET, resources),
        is_reusable=True,
    )
    httpx_mock.add_response(url=AAX_URL, content=_aax_book(), is_reusable=True)


@pytest.fixture
def projections(httpx_mock):
    httpx_mock.add_response(
        url=re.compile(
            rf".*package_show\?id=(alberta-population-projections-2026-2051|{PROJ_DATASET})$"
        ),
        json=_projection_package(),
        is_reusable=True,
    )


async def test_activity_index_defaults_to_the_latest_24_months(aax):
    result = await client.get_activity_index()
    assert result.total_observations == 30
    assert result.first_period == "1981-01" and result.last_period == "1983-06"
    assert len(result.observations) == 24
    assert result.observations[-1].period == "1983-06"
    assert result.series == "Alberta Activity Index (January 1981 = 100)"
    assert result.attribution and "Open Government Licence" in result.attribution
    assert result.provenance.limits and "latest 24 months" in result.provenance.limits
    assert "Open Government Licence" in (result.provenance.licence or "")


async def test_activity_index_range_and_last_n(aax):
    result = await client.get_activity_index(start="1981-01", end="1981-12", last_n=3)
    assert [p.period for p in result.observations] == ["1981-10", "1981-11", "1981-12"]
    assert result.provenance.limits is None
    whole = await client.get_activity_index(start="1981-01")
    assert len(whole.observations) == 30
    assert whole.observations[0].value == pytest.approx(100.0)


@pytest.mark.parametrize("kwargs", [{"start": "1981"}, {"end": "2024-13"}, {"last_n": 0}])
async def test_activity_index_refuses_bad_arguments(kwargs):
    with pytest.raises(InvalidInput):
        await client.get_activity_index(**kwargs)


async def test_activity_index_in_french(aax):
    result = await client.get_activity_index(lang="fr")
    assert result.provenance.coverage and "Indice d'activité" in result.provenance.coverage


async def test_provincial_projection_reads_the_scenario_sheet(httpx_mock, projections):
    httpx_mock.add_response(url=_url("all"), content=_scenario_book(), is_reusable=True)
    medium = await client.get_population_projection()
    assert medium.edition == 2026 and medium.area is None
    assert medium.areas == ["Low Scenario", "Med Scenario", "High Scenario"]
    assert [(r.year, r.gender, r.projected) for r in medium.rows] == [
        (2001, "all", False),
        (2025, "all", False),
        (2026, "all", True),
        (2051, "all", True),
    ]
    assert medium.rows[-1].total == 2000 + 2051 and medium.rows[-1].ages is None
    high = await client.get_population_projection(
        scenario="high", gender="any", start_year=2051, ages=True
    )
    assert {r.gender for r in high.rows} == {"women+", "men+", "all"}
    ages = high.rows[0].ages or {}
    assert list(ages)[:2] == ["0", "1"] and list(ages)[-1] == "100" and len(ages) == 101
    women = await client.get_population_projection(scenario="low", gender="women+", end_year=2001)
    assert [(r.year, r.gender) for r in women.rows] == [(2001, "women+")]


async def test_sub_provincial_projection_lists_then_reads_an_area(httpx_mock, projections):
    httpx_mock.add_response(
        url=_url("cd"), content=_areas_book(["4801", "4806", "4811"]), is_reusable=True
    )
    listing = await client.get_population_projection(geography="census_division")
    assert listing.rows == [] and listing.areas == ["4801", "4806", "4811"]
    assert listing.provenance.limits and "no area was given" in listing.provenance.limits
    calgary = await client.get_population_projection(
        geography="census_division", area="4806", start_year=2026, end_year=2026
    )
    assert calgary.area == "4806"
    assert [(r.year, r.total) for r in calgary.rows] == [(2026, 200 + 2026)]
    with pytest.raises(InvalidInput, match="matches 3 areas"):
        await client.get_population_projection(geography="census_division", area="48")


async def test_lga_is_not_taken_for_the_aggregated_file(httpx_mock, projections):
    httpx_mock.add_response(url=_url("lga"), content=_areas_book(["Banff"]), is_reusable=True)
    result = await client.get_population_projection(
        geography="local_geographic_area", area="banff", start_year=2051
    )
    assert result.url == _url("lga") and result.area == "Banff"


async def test_projection_argument_checks():
    with pytest.raises(InvalidInput, match="medium scenario"):
        await client.get_population_projection(geography="economic_region", scenario="low")
    with pytest.raises(InvalidInput, match="leave it unset"):
        await client.get_population_projection(area="4806")
    with pytest.raises(InvalidInput, match="start_year"):
        await client.get_population_projection(start_year=2030, end_year=2020)
    with pytest.raises(InvalidInput, match="edition"):
        await client.get_population_projection(edition=2023)


async def test_without_an_edition_this_year_and_the_last_known_are_tried(httpx_mock, monkeypatch):
    monkeypatch.setattr(constants, "PROJECTIONS_LATEST_KNOWN", 2025)
    this_year = datetime.now().year
    httpx_mock.add_response(
        url=re.compile(r".*package_show\?id=alberta-population-projections-20\d\d-2051$"),
        status_code=404,
        json={"success": False, "error": {"message": "Not found", "__type": "Not Found Error"}},
        is_reusable=True,
    )
    with pytest.raises(NotFound, match=f"alberta-population-projections-{this_year}-2051"):
        await client.get_population_projection_summary()


async def test_summary_maps_footnoted_headers(httpx_mock, projections):
    httpx_mock.add_response(url=_url("summary"), content=_summary_book(), is_reusable=True)
    summary = await client.get_population_projection_summary()
    first, last = summary.rows
    assert (first.year, first.projected, last.projected) == (2001, False, True)
    assert first.total_fertility_rate is None and first.births == 37202
    assert last.population == 6959145 and last.period == "2050-51"
    assert (last.child_dependency_ratio, last.elderly_dependency_ratio) == (23.9, 32.9)
    assert (last.net_interprovincial, last.total_net_migration) == (13000, 74400)
    assert last.net_non_permanent_residents == 2500
    assert summary.provenance.limits is None
    only = await client.get_population_projection_summary(start_year=2051)
    assert [r.year for r in only.rows] == [2051]


async def test_summary_names_a_missing_column(httpx_mock, projections):
    httpx_mock.add_response(url=_url("summary"), content=_summary_book(drop_births=True))
    summary = await client.get_population_projection_summary()
    assert summary.rows[-1].births is None
    assert summary.provenance.limits and "births" in summary.provenance.limits


async def test_a_changed_layout_is_an_upstream_error(httpx_mock, projections):
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["Region", "Gender", "Count", "Other"])
    sheet.append(["Alberta", "All", 1, 2])
    httpx_mock.add_response(url=_url("summary"), content=_bytes(book))
    with pytest.raises(UpstreamError, match="layout"):
        await client.get_population_projection_summary()
