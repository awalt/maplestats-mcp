"""wds_query_table: SQL over a slice of a whole table, read from its full-table CSV.

Checked live on 2026-11-20: the LFS table 14-10-0287 (5.5 million rows) streamed and
filtered in about 16 s at a 158 MB peak; the same slice read from the file and
rebuilt from WDS by coordinate (the route when the file answers with StatCan's
captcha) gave identical rows. The file here keeps the live CSV's columns, order and
quoting, with a two-province, two-characteristic table and its real member ids.
"""

from __future__ import annotations

from datetime import date

import pytest

from maplestats_mcp.modules.statcan.wds import client, table_query, tools
from maplestats_mcp.modules.statcan.wds.schemas import ObservationRow, VectorData, VectorSeries
from maplestats_mcp.shared.envelope import make_provenance
from maplestats_mcp.shared.errors import InvalidInput, NotFound
from maplestats_mcp.shared.remote_zip import ZipMember

PID = 14100287
HEADER = (
    '﻿"REF_DATE","GEO","DGUID","Labour force characteristics","Data type","UOM","UOM_ID",'
    '"SCALAR_FACTOR","SCALAR_ID","VECTOR","COORDINATE","VALUE","STATUS","SYMBOL","TERMINATED",'
    '"DECIMALS"'
)
# (geo id, geo, characteristic id, characteristic, unit, scalar id, vector)
SERIES = [
    (1, "Canada", 3, "Employment", "Persons in thousands", 3, 2062811),
    (7, "Ontario", 3, "Employment", "Persons in thousands", 3, 2063945),
    (10, "Alberta", 3, "Employment", "Persons in thousands", 3, 2064512),
    (7, "Ontario", 7, "Unemployment rate", "Percent", 0, 2063949),
    (10, "Alberta", 7, "Unemployment rate", "Percent", 0, 2064516),
]
VALUES = {2062811: 21000.0, 2063945: 8200.0, 2064512: 2600.0, 2063949: 7.5, 2064516: 7.0}


def _csv() -> bytes:
    lines = [HEADER]
    for month in ("2025-11", "2025-12", "2026-01"):
        for geo_id, geo, char_id, char, unit, scalar, vector in SERIES:
            scale = "thousands" if scalar == 3 else "units"
            status = "E" if (vector == 2064516 and month == "2026-01") else ""
            lines.append(
                f'"{month}","{geo}","2021A00011","{char}","Seasonally adjusted","{unit}","0",'
                f'"{scale}","{scalar}","v{vector}","{geo_id}.{char_id}.1","{VALUES[vector]}",'
                f'"{status}","","","1"'
            )
    return "\n".join(lines).encode("utf-8")


def _cube() -> dict:
    def dim(position, name, members, has_uom=False):
        return {
            "dimensionPositionId": position,
            "dimensionNameEn": name,
            "dimensionNameFr": name,
            "hasUom": has_uom,
            "member": [
                {
                    "memberId": mid,
                    "memberNameEn": label,
                    "parentMemberId": parent,
                    "memberUomCode": uom,
                }
                for mid, label, parent, uom in members
            ],
        }

    return {
        "productId": str(PID),
        "cubeTitleEn": "Labour force characteristics, monthly, seasonally adjusted and trend-cycle",
        "cubeTitleFr": "Caractéristiques de la population active",
        "cubeStartDate": "2025-11-01",
        "cubeEndDate": "2026-01-01",
        "releaseTime": "2026-11-06T08:30",
        "frequencyCode": 6,
        "dimension": [
            dim(
                1,
                "Geography",
                [(1, "Canada", None, None), (7, "Ontario", 1, None), (10, "Alberta", 1, None)],
            ),
            dim(
                2,
                "Labour force characteristics",
                [(3, "Employment", None, 428), (7, "Unemployment rate", None, 239)],
                has_uom=True,
            ),
            dim(3, "Data type", [(1, "Seasonally adjusted", None, None)]),
        ],
    }


class _FakeStream:
    """MemberStream's blocks() over an in-memory CSV, a few lines per block."""

    def __init__(self, url, member, **kwargs) -> None:
        self.lines = _csv().split(b"\n")

    async def blocks(self):
        for at in range(0, len(self.lines), 4):
            yield b"\n".join(self.lines[at : at + 4])


@pytest.fixture
def table(monkeypatch, httpx_mock):
    async def cube(pid):
        return _cube(), False

    real_get = client._get

    async def get(method, **kwargs):
        if method != "getFullTableDownloadCSV":
            return await real_get(method, **kwargs)
        return {
            "status": "SUCCESS",
            "object": "https://www150.statcan.gc.ca/n1/tbl/csv/14100287-eng.zip",
        }

    async def check(url):
        return "downloadable"

    async def members(url):
        return [ZipMember("14100287.csv", 1000, len(_csv()), 8, 0)], 2

    monkeypatch.setattr(client, "cube_metadata_raw", cube)
    monkeypatch.setattr(client, "_get", get)
    monkeypatch.setattr(client, "check_file", check)
    monkeypatch.setattr(table_query, "list_members", members)
    monkeypatch.setattr(table_query, "MemberStream", _FakeStream)


async def _query(sql: str, **kwargs):
    fn = getattr(tools.wds_query_table, "fn", tools.wds_query_table)
    return await fn(product_id=PID, sql=sql, **kwargs)


async def test_a_slice_is_queried_with_one_column_per_dimension(table):
    result = await _query(
        "SELECT geography, value FROM obs WHERE labour_force_characteristics = 'Unemployment rate' "
        "AND ref_period = DATE '2026-01-01' ORDER BY value DESC"
    )
    assert result.rows == [["Ontario", 7.5], ["Alberta", 7.0]]
    assert result.source == "full-table file"
    assert result.rows_read == 15 and result.input_rows == 15
    assert result.dimension_columns == {
        "Geography": "geography_member",
        "Labour force characteristics": "labour_force_characteristics",
        "Data type": "data_type",
    }
    assert result.citation.startswith("Statistics Canada. Table 14-10-0287-01, Labour force")


async def test_a_follow_up_query_on_the_same_slice_reads_it_from_memory(table, monkeypatch):
    # Agreed with the owner on 2026-11-21: the LFS slice took about 16 s to read, and a
    # second SQL over the same members and periods is common.
    opened: list[str] = []
    real = _FakeStream.blocks

    def counting(self):
        opened.append("file")
        return real(self)

    monkeypatch.setattr(_FakeStream, "blocks", counting)
    first = await _query("SELECT count(*) FROM obs", members={"Geography": ["Alberta"]})
    second = await _query(
        "SELECT count(DISTINCT vector_id) FROM obs", members={"Geography": ["Alberta"]}
    )
    assert opened == ["file"]
    assert first.provenance.cached is False and second.provenance.cached is True
    assert second.input_rows == first.input_rows and second.source == "full-table file"
    assert "earlier call" in (second.provenance.coverage or "")
    # Other members, other periods, a new release or an old slice: read again.
    await _query("SELECT 1 FROM obs", members={"Geography": ["Ontario"]})
    await _query("SELECT 1 FROM obs", members={"Geography": ["Alberta"]}, start_period="2026")
    assert len(opened) == 3
    monkeypatch.setattr(table_query, "SLICE_CACHE_SECONDS", -1)
    await _query("SELECT 1 FROM obs", members={"Geography": ["Alberta"]})
    assert len(opened) == 4


async def test_kept_slices_stay_under_the_row_limit(table, monkeypatch):
    monkeypatch.setattr(table_query, "SLICE_CACHE_ROWS", 6)
    await _query("SELECT 1 FROM obs", members={"Geography": ["Alberta"]})
    await _query("SELECT 1 FROM obs", members={"Geography": ["Ontario"]})
    kept = list(table_query._SLICES.values())
    assert sum(len(k.rows) for k in kept) <= 6
    # The newest stays; the oldest went first.
    assert kept and {r[-3] for r in kept[-1].rows} == {"Ontario"}


async def test_members_and_periods_narrow_the_slice(table):
    result = await _query(
        "SELECT count(*), min(ref_period) FROM obs",
        members={"Geography": ["Alberta"]},
        start_period="2025-12",
    )
    assert result.rows == [[4, "2025-12-01"]]
    assert result.rows_read == 15


async def test_the_obs_columns_are_filled_from_the_file(table):
    result = await _query(
        "SELECT unit, scale, scale_multiplier, adjustment, quality, series_title FROM obs "
        "WHERE vector_id = 2064516 AND ref_period = DATE '2026-01-01'"
    )
    assert result.rows == [
        [
            "Percent",
            "units",
            1,
            "seasonally adjusted",
            "E",
            "Alberta;Unemployment rate;Seasonally adjusted",
        ]
    ]


async def test_the_checks_refuse_a_total_with_its_parts(table):
    with pytest.raises(InvalidInput, match="total_with_parts"):
        await _query(
            "SELECT ref_period, sum(value) FROM obs "
            "WHERE labour_force_characteristics = 'Employment' GROUP BY 1"
        )


async def test_the_checks_warn_about_an_average_of_rates(table):
    result = await _query(
        "SELECT ref_period, avg(value) FROM obs "
        "WHERE labour_force_characteristics = 'Unemployment rate' GROUP BY 1"
    )
    kinds = [w.split(":")[0] for w in result.warnings]
    assert kinds == ["average_of_rates", "quality"]


async def test_a_misspelled_member_fails_before_the_download(table, monkeypatch):
    async def no_download(*args, **kwargs):
        raise AssertionError("the file must not be read")

    monkeypatch.setattr(table_query, "_from_file", no_download)
    with pytest.raises(InvalidInput, match="did you mean 'Employment'"):
        await _query("SELECT avg(value) FROM obs WHERE labour_force_characteristics = 'Employmnt'")


async def test_unknown_members_and_bad_periods_are_refused(table):
    with pytest.raises(InvalidInput, match="saskatoon"):
        await _query("SELECT 1 FROM obs", members={"Geography": ["Saskatoon"]})
    with pytest.raises(InvalidInput, match="start_period"):
        await _query("SELECT 1 FROM obs", start_period="Jan 2025")


async def test_an_empty_slice_is_not_found(table):
    with pytest.raises(NotFound):
        await _query("SELECT 1 FROM obs", start_period="2030")


async def test_a_table_over_the_size_limit_is_refused(table, monkeypatch):
    async def big(url):
        return [ZipMember("14100287.csv", table_query.MAX_ZIP_BYTES + 1, 10**10, 8, 0)], 2

    monkeypatch.setattr(table_query, "list_members", big)
    with pytest.raises(InvalidInput, match="over the 200 MB"):
        await _query("SELECT 1 FROM obs")


async def test_a_blocked_file_is_rebuilt_from_wds(table, monkeypatch):
    async def blocked(url):
        return "blocked"

    asked: list[list[str]] = []

    async def coords(pid, coordinates, latest_n):
        asked.append(coordinates)
        series = []
        for coordinate in coordinates:
            geo, char = (int(p) for p in coordinate.split(".")[:2])
            match = next(s for s in SERIES if s[0] == geo and s[2] == char)
            series.append(
                VectorSeries(
                    product_id=pid,
                    coordinate=coordinate,
                    vector_id=match[6],
                    observations=[
                        ObservationRow(
                            ref_period=date(2026, 1, 1),
                            value=VALUES[match[6]],
                            decimals=1,
                            scalar_factor_code=match[5],
                            scale_multiplier=10 ** match[5],
                            symbol_code=0,
                            status_code=0,
                            security_level_code=0,
                        )
                    ],
                )
            )
        return VectorData(
            product_id=pid,
            coordinate=coordinates[0],
            vector_id=0,
            observations=[],
            series=series,
            provenance=make_provenance(
                source="statcan-wds", url="https://x", cached=False, schema_name="s"
            ),
        )

    monkeypatch.setattr(client, "check_file", blocked)
    monkeypatch.setattr(client, "get_data_from_cube_pid_coords_and_latest_n_periods", coords)
    result = await _query(
        "SELECT geography, unit, scale, value FROM obs ORDER BY vector_id",
        members={"Geography": ["Ontario"]},
    )
    assert result.source == "WDS by coordinate"
    assert asked == [["7.3.1.0.0.0.0.0.0.0", "7.7.1.0.0.0.0.0.0.0"]]
    assert result.rows == [
        ["Ontario", "Persons in thousands", "thousands", 8200.0],
        ["Ontario", "Percent", "units", 7.5],
    ]


def test_dimension_columns_never_shadow_an_obs_column():
    taken = {"geography", "unit"}
    assert table_query.dimension_column("Geography", taken) == "geography_member"
    assert table_query.dimension_column("Age group", taken) == "age_group"
    assert table_query.dimension_column("2021 boundaries", taken) == "d_2021_boundaries"
