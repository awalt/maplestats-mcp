"""wds_get_full_table_download's WDS rebuild: its size, its member checks, and its script.

Since November 2026 StatCan blocks scripted downloads of full-table zips but still
serves WDS. The script asks WDS for every series and writes StatCan's CSV layout;
live on 2026-11-18 its output was byte for byte StatCan's own file for 36-10-0104,
18-10-0004 (from 2024-01) and 14-10-0287 (from 2025-06). The idea comes from
vrraiv/sixfigures PR #105 (reimplemented: that repository has no licence file).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maplestats_mcp.modules.reproduce import wds_table
from maplestats_mcp.modules.statcan.wds import client
from maplestats_mcp.shared.errors import InvalidInput

WDS = "https://www150.statcan.gc.ca/t1/wds/rest/"


def _member(mid, name, **extra):
    return {
        "memberId": mid,
        "memberNameEn": name,
        "terminated": 0,
        "memberUomCode": None,
        "vintage": None,
        "geoLevel": None,
        "classificationCode": None,
        **extra,
    }


CUBE = {
    "productId": "99100001",
    "cubeStartDate": "2026-01-01",
    "cubeEndDate": "2026-03-01",
    "frequencyCode": 6,
    "nbSeriesCube": 3,
    "dimension": [
        {
            "dimensionPositionId": 1,
            "dimensionNameEn": "Geography",
            "hasUom": False,
            "member": [
                _member(1, "Canada", vintage=2016, geoLevel=0, classificationCode="11124"),
                _member(
                    5, "Toronto, Ontario", vintage=2011, geoLevel=503, classificationCode="535"
                ),
            ],
        },
        {
            "dimensionPositionId": 2,
            "dimensionNameEn": "Products",
            "hasUom": True,
            # Listed out of id order: the CSV follows this order, not the ids.
            "member": [
                _member(7, "All-items", memberUomCode=17),
                _member(2, "Food", memberUomCode=17),
            ],
        },
    ],
}

CODES = {
    "uom": [{"memberUomCode": 17, "memberUomEn": "2002=100"}],
    "scalar": [{"scalarFactorCode": 0, "scalarFactorDescEn": "units"}],
    "status": [
        {"statusCode": "0", "statusRepresentationEn": None},
        {"statusCode": "1", "statusRepresentationEn": ".."},
    ],
    "symbol": [
        {"symbolCode": "0", "symbolRepresentationEn": None},
        {"symbolCode": "1", "symbolRepresentationEn": "p"},
    ],
    "securityLevel": [
        {"securityLevelCode": 0, "securityLevelRepresentationEn": None},
        {"securityLevelCode": 1, "securityLevelRepresentationEn": "x"},
    ],
}


def _point(month, value, status=0, symbol=0, secret=0, released: str | None = "2026-04-15T08:30"):
    return {
        "refPer": f"2026-0{month}-01",
        "value": value,
        "decimals": 1,
        "scalarFactorCode": 0,
        "symbolCode": symbol,
        "statusCode": status,
        "securityLevelCode": secret,
        "releaseTime": released,
    }


def _series(coordinate, vector, points):
    return {"status": "SUCCESS", "object": {"coordinate": coordinate, "vectorId": vector,
                                            "vectorDataPoint": points}}  # fmt: skip


@pytest.fixture
def cube(monkeypatch):
    async def metadata(pid):
        return CUBE, True

    monkeypatch.setattr(client, "cube_metadata_raw", metadata)


async def test_the_rebuild_is_sized_and_scripted(cube):
    rebuild, scripts = await client._rebuild(99100001, None, None, None)
    assert rebuild is not None
    assert (rebuild.combinations, rebuild.periods_per_series, rebuild.wds_calls) == (4, 4, 1)
    assert rebuild.within_limit and scripts[0].language == "python"
    assert "PRODUCT_ID = 99100001" in scripts[0].code
    assert "Mozilla" not in scripts[0].code  # it names itself


async def test_members_and_periods_narrow_the_rebuild(cube):
    rebuild, scripts = await client._rebuild(99100001, {"geography": ["canada"]}, "2026-02", None)
    assert rebuild is not None and rebuild.combinations == 2
    assert "MEMBERS = {'geography': ['canada']}" in scripts[0].code
    assert "START_PERIOD = '2026-02'" in scripts[0].code


async def test_an_unknown_dimension_member_or_period_is_refused(cube):
    with pytest.raises(InvalidInput, match="no dimension"):
        await client._rebuild(99100001, {"Sex": ["Males"]}, None, None)
    with pytest.raises(InvalidInput, match="not in 'Geography'"):
        await client._rebuild(99100001, {"Geography": ["Atlantis"]}, None, None)
    with pytest.raises(InvalidInput, match="start_period"):
        await client._rebuild(99100001, None, "January 2026", None)


async def test_a_rebuild_past_the_limit_has_no_script(cube, monkeypatch):
    monkeypatch.setattr(wds_table, "MAX_CALLS", 0)
    rebuild, scripts = await client._rebuild(99100001, None, None, None)
    assert rebuild is not None and not rebuild.within_limit and scripts == []
    assert "over the limit" in client._rebuild_notes(rebuild, "en")[0]


def test_the_script_writes_statcans_csv_layout_with_its_code_sets(httpx_mock, tmp_path):
    httpx_mock.add_response(
        url=f"{WDS}getCubeMetadata", json=[{"status": "SUCCESS", "object": CUBE}]
    )
    httpx_mock.add_response(url=f"{WDS}getCodeSets", json={"status": "SUCCESS", "object": CODES})
    httpx_mock.add_response(
        url=f"{WDS}getDataFromCubePidCoordAndLatestNPeriods",
        # Out of the order asked, as WDS answers; Toronto x Food is not published.
        json=[
            _series("5.7.0.0.0.0.0.0.0.0", 103, [_point(1, None, secret=1), _point(2, 30.8)]),
            {"status": "FAILED", "object": {"coordinate": "5.2.0.0.0.0.0.0.0.0"}},
            _series("1.2.0.0.0.0.0.0.0.0", 102, [_point(1, None, status=1), _point(2, 25.0)]),
            _series(
                "1.7.0.0.0.0.0.0.0.0",
                101,
                # The last point is WDS padding (no release time): left out.
                [_point(1, 19.7), _point(2, 20.25, symbol=1), _point(3, None, 1, released=None)],
            ),
        ],
    )
    namespace: dict = {"__name__": "rebuild"}
    exec(wds_table.rebuild_script(99100001), namespace)  # noqa: S102
    namespace["OUTPUT"] = tmp_path / "table.csv"
    namespace["main"]()
    request = json.loads(httpx_mock.get_requests()[-1].content)
    assert [r["coordinate"] for r in request][:2] == ["1.7.0.0.0.0.0.0.0.0", "1.2.0.0.0.0.0.0.0.0"]
    assert {r["latestN"] for r in request} == {4}
    text = Path(namespace["OUTPUT"]).read_bytes().decode("utf-8")
    assert text.startswith("﻿")
    h = '"REF_DATE","GEO","DGUID","Products","UOM","UOM_ID","SCALAR_FACTOR","SCALAR_ID",'
    h += '"VECTOR","COORDINATE","VALUE","STATUS","SYMBOL","TERMINATED","DECIMALS"'
    canada = '"Canada","2016A000011124"'
    toronto = '"Toronto, Ontario","2011S0503535"'
    tail = '"2002=100","17","units","0"'
    assert text[1:].split("\n") == [
        h,
        f'"2026-01",{canada},"All-items",{tail},"v101","1.7","19.7","","","","1"',
        f'"2026-01",{canada},"Food",{tail},"v102","1.2","","..","","","1"',
        f'"2026-01",{toronto},"All-items",{tail},"v103","5.7","","x","","","1"',
        f'"2026-02",{canada},"All-items",{tail},"v101","1.7","20.2","","p","","1"',
        f'"2026-02",{canada},"Food",{tail},"v102","1.2","25.0","","","","1"',
        f'"2026-02",{toronto},"All-items",{tail},"v103","5.7","30.8","","","","1"',
        "",
    ]


@pytest.mark.parametrize(
    ("start", "expected"),
    [("2025", 23), ("2025-01", 23), ("2025-01-15", 23), (None, 611)],
)
def test_periods_to_ask_reads_every_ref_date_form(start, expected):
    """A bare year raised ValueError from wds_get_full_table_download until 2026-11-20."""
    monthly = {"cubeStartDate": "1976-01-01", "cubeEndDate": "2026-10-01", "frequencyCode": 6}
    assert wds_table.periods_to_ask(monthly, start) == expected
