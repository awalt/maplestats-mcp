"""Tests for calgary/client.py, shaped around what data.calgary.ca returned live on
2026-11-19: numbers and dates as strings, aggregates under their $select alias, month
keys as floating timestamps, and a rejected SoQL query as HTTP 400 with a
"query.soql.*" message (see modules/socrata/client.py)."""

from __future__ import annotations

import re
from typing import Any

import httpx
import pytest

from maplestats_mcp.modules.calgary import client, constants
from maplestats_mcp.shared import cache as cache_module
from maplestats_mcp.shared.errors import InvalidInput, NotFound

_PERMITS = re.compile(
    re.escape(f"https://{constants.DOMAIN}/resource/{constants.PERMITS_DATASET}.json") + r".*"
)
_POPULATION = re.compile(
    re.escape(f"https://{constants.DOMAIN}/resource/{constants.POPULATION_DATASET}.json") + r".*"
)
_VIEWS = re.compile(re.escape(f"https://{constants.DOMAIN}/api/views/") + r".*")

# One row as the live API returned it (2026-11-19), location columns left out.
_PERMIT_ROW = {
    "permitnum": "BP2026-20514",
    "statuscurrent": "Issued Permit",
    "applieddate": "2026-10-26T00:00:00.000",
    "issueddate": "2026-11-13T00:00:00.000",
    "permittypemapped": "Building",
    "permitclassmapped": "Non-Residential",
    "permitclassgroup": "Industrial",
    "workclassgroup": "Unspecified",
    "description": "Fire alarm system installation",
    "applicantname": "GLOBALTECH GROUP",
    "housingunits": "0",
    "estprojectcost": "11330",
    "originaladdress": "1010C MEMORIAL DR NE",
    "communitycode": "BRD",
    "communityname": "BRIDGELAND/RIVERSIDE",
    "latitude": "51.04935587284983",
    "longitude": "-114.03986150832544",
}
_VIEW = {"id": constants.PERMITS_DATASET, "name": "Building Permits", "rowsUpdatedAt": 1795633418}


@pytest.fixture(autouse=True)
def _clear_cache():
    cache_module._caches.clear()
    yield


def _params(request: httpx.Request) -> dict[str, str]:
    return dict(request.url.params)


def _route(httpx_mock, responses: dict[str, Any], seen: list[dict[str, str]]) -> None:
    """Answer each permit query by its $select: the first key found in it wins."""

    def answer(request: httpx.Request) -> httpx.Response:
        params = _params(request)
        seen.append(params)
        select = params.get("$select", "")
        for key, body in responses.items():
            if key in select:
                return httpx.Response(200, json=body)
        raise AssertionError(f"unexpected $select {select!r}")

    httpx_mock.add_callback(answer, url=_PERMITS, is_reusable=True)
    httpx_mock.add_response(url=_VIEWS, json=_VIEW, is_reusable=True, is_optional=True)


def test_where_matches_name_or_code_quotes_and_makes_end_inclusive():
    where = client.build_permit_where(
        community=" o'brien ",
        work_class_group="new",
        date_field="applied",
        start_date="2026-01-01",
        end_date="2026-01-31",
        address_contains="17 av_sw%",
        min_housing_units=2,
    )
    assert "(upper(communityname) = 'O''BRIEN' OR upper(communitycode) = 'O''BRIEN')" in where
    assert "upper(workclassgroup) = 'NEW'" in where
    assert "applieddate >= '2026-01-01T00:00:00'" in where
    assert "applieddate < '2026-02-01T00:00:00'" in where
    # LIKE wildcards in the input are dropped, not passed through.
    assert "upper(originaladdress) like '%17 AVSW%'" in where
    assert "housingunits >= 2" in where


def test_where_is_empty_without_filters():
    assert client.build_permit_where() == ""


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start_date": "2026-13-01"},
        {"start_date": "2026-02-01", "end_date": "2026-01-01"},
        {"date_field": "decided"},
    ],
)
def test_where_rejects_bad_dates_in_both_languages(kwargs):
    with pytest.raises(InvalidInput):
        client.build_permit_where(**kwargs)
    with pytest.raises(InvalidInput, match="AAAA-MM-JJ|précède|l'une des valeurs"):
        client.build_permit_where(**kwargs, lang="fr")


async def test_list_types_string_values_and_counts_every_match(httpx_mock):
    seen: list[dict[str, str]] = []
    _route(httpx_mock, {"count(*)": [{"total": "641"}], "permitnum": [_PERMIT_ROW]}, seen)
    result = await client.list_building_permits(community="brd", limit=1)
    permit = result.permits[0]
    assert permit.issued_date is not None and permit.issued_date.isoformat() == "2026-11-13"
    assert permit.completed_date is None
    assert permit.housing_units == 0
    assert permit.estimated_cost == 11330.0
    assert permit.contractor is None
    assert result.total_matches == 641
    assert result.provenance.as_of is not None
    assert result.provenance.licence and "City of Calgary" in result.provenance.licence
    rows_query = next(p for p in seen if "permitnum" in p["$select"])
    assert rows_query["$order"] == "issueddate DESC NULL LAST, permitnum DESC"
    assert "upper(communitycode) = 'BRD'" in rows_query["$where"]


async def test_list_keeps_rows_when_the_metadata_call_fails(httpx_mock):
    httpx_mock.add_callback(
        lambda request: httpx.Response(
            200,
            json=[{"total": "1"}] if "count" in _params(request)["$select"] else [_PERMIT_ROW],
        ),
        url=_PERMITS,
        is_reusable=True,
    )
    httpx_mock.add_response(url=_VIEWS, status_code=503, is_reusable=True)
    result = await client.list_building_permits(limit=1)
    assert result.permits and result.provenance.as_of is None


async def test_list_rejects_limit_over_the_cap():
    with pytest.raises(InvalidInput, match="between 1 and 500"):
        await client.list_building_permits(limit=501)


async def test_summary_by_month_returns_date_order_and_short_keys(httpx_mock):
    seen: list[dict[str, str]] = []
    grouped = [
        {
            "group_key": "2026-11-01T00:00:00.000",
            "permit_count": "1067",
            "housing_units": "1251",
            "estimated_cost": "415017201.41",
        },
        {"group_key": "2026-10-01T00:00:00.000", "permit_count": "1997"},
    ]
    totals = [{"permit_count": "3064", "housing_units": "3586", "estimated_cost": "1071390178.87"}]
    _route(httpx_mock, {"group_key": grouped, "count(*)": totals}, seen)
    result = await client.summarize_building_permits("month", start_date="2026-10-01", top=2)
    assert [g.key for g in result.groups] == ["2026-10", "2026-11"]
    # A group with no sums upstream counts as zero, not as a missing value.
    assert result.groups[0].housing_units == 0 and result.groups[0].estimated_cost == 0.0
    assert result.total_permits == 3064
    group_query = next(p for p in seen if "group_key" in p["$select"])
    assert group_query["$select"].startswith("date_trunc_ym(issueddate) AS group_key")
    assert group_query["$order"] == "group_key DESC"
    assert group_query["$limit"] == "2"
    assert "issueddate IS NOT NULL" in group_query["$where"]


async def test_summary_by_label_orders_largest_first(httpx_mock):
    seen: list[dict[str, str]] = []
    grouped = [{"group_key": "Single Family", "permit_count": "16595", "housing_units": "8254"}]
    _route(
        httpx_mock,
        {"group_key": grouped, "count(*)": [{"permit_count": "41600"}]},
        seen,
    )
    result = await client.summarize_building_permits("permit_class_group", top=1)
    assert result.groups[0].key == "Single Family"
    group_query = next(p for p in seen if "group_key" in p["$select"])
    assert group_query["$select"].startswith("permitclassgroup AS group_key")
    assert group_query["$order"] == "permit_count DESC, group_key"
    assert "$where" not in group_query


async def test_rejected_soql_surfaces_socratas_reason(httpx_mock):
    httpx_mock.add_response(
        url=_PERMITS,
        status_code=400,
        json={
            "message": "Query coordinator error: query.soql.no-such-column; No such column: "
            "x; position: Map(row -> 1)",
            "errorCode": "query.soql.no-such-column",
        },
    )
    with pytest.raises(InvalidInput, match="No such column: x"):
        await client.summarize_building_permits("community")


async def test_population_rows_and_sums(httpx_mock):
    rows = [
        {
            "name": "BRIDGELAND/RIVERSIDE",
            "comm_code": "BRD",
            "census_year": "2019",
            "population": "6829",
            "occupied_dwellings": "3979",
            "persons_per_unit": "1.72",
        }
    ]
    sums = [{"census_year": "2019", "population": "1278432", "occupied_dwellings": "517771"}]
    httpx_mock.add_callback(
        lambda request: httpx.Response(
            200, json=sums if "sum(" in _params(request)["$select"] else rows
        ),
        url=_POPULATION,
        is_reusable=True,
    )
    httpx_mock.add_response(url=_VIEWS, json=_VIEW, is_reusable=True)
    community = await client.get_community_populations(community="brd", start_year=2015)
    assert community.rows[0].persons_per_unit == 1.72
    assert community.rows[0].community_code == "BRD"
    assert "census_year >= 2015" in community.where
    city = await client.get_community_populations(by="total", lang="fr")
    assert city.rows[0].community is None and city.rows[0].population == 1278432
    assert city.provenance.licence and "Ville de Calgary" in city.provenance.licence


async def test_population_unknown_community_is_not_found(httpx_mock):
    httpx_mock.add_response(url=_POPULATION, json=[])
    with pytest.raises(NotFound, match="three-letter code"):
        await client.get_community_populations(community="Nowhere")


async def test_population_rejects_reversed_years():
    with pytest.raises(InvalidInput, match="précède"):
        await client.get_community_populations(start_year=2019, end_year=2010, lang="fr")
