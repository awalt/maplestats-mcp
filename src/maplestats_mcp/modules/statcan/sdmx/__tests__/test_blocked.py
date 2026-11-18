"""SDMX behind StatCan's captcha: the same series come from WDS.

Live 2026-11-18 from a cloud host: every /t1/wds/sdmx/ request answered HTTP 403
with Cf-Mitigated: challenge, while WDS (/t1/wds/rest/) on the same host answered.
The WDS client functions are replaced here; their own tests cover their requests.
"""

from __future__ import annotations

from datetime import date

import pytest

from maplestats_mcp.modules.statcan.sdmx import client, constants
from maplestats_mcp.modules.statcan.sdmx.schemas import SdmxCode, SdmxDimension
from maplestats_mcp.modules.statcan.wds import client as wds_client
from maplestats_mcp.modules.statcan.wds.schemas import (
    ObservationRow,
    VectorData,
    VectorDataSet,
    VectorSeries,
)
from maplestats_mcp.shared.envelope import make_provenance
from maplestats_mcp.shared.errors import InvalidInput

_DATA_URL = f"{constants.BASE_URL}data/DF_18100004/"

_METADATA = {
    "productId": "18100004",
    "frequencyCode": 6,
    "cubeStartDate": "1914-01-01",
    "cubeEndDate": "2026-10-01",
    "dimension": [
        {
            "dimensionPositionId": 1,
            "dimensionNameEn": "Geography",
            "dimensionNameFr": "Géographie",
            "hasUom": False,
            "member": [
                {"memberId": 2, "memberNameEn": "Canada", "memberNameFr": "Canada"},
                {"memberId": 3, "memberNameEn": "Ontario", "memberNameFr": "Ontario"},
            ],
        },
        {
            "dimensionPositionId": 2,
            "dimensionNameEn": "Products and product groups",
            "dimensionNameFr": "Produits et groupes de produits",
            "hasUom": True,
            "member": [
                {
                    "memberId": 2,
                    "memberNameEn": "All-items",
                    "memberNameFr": "Ensemble",
                    "memberUomCode": 17,
                },
            ],
        },
    ],
}


def _row(day: date, value: float, status: int = 0) -> ObservationRow:
    return ObservationRow(
        ref_period=day,
        value=value,
        decimals=1,
        scalar_factor_code=0,
        symbol_code=0,
        status_code=status,
        security_level_code=0,
        status="use with caution" if status else None,
    )


def _series(coordinate: str, vector: int, rows: list[ObservationRow]) -> VectorSeries:
    return VectorSeries(
        product_id=18100004,
        coordinate=f"{coordinate}.0.0.0.0.0.0.0.0",
        vector_id=vector,
        observations=rows,
    )


_PROVENANCE = make_provenance(
    source="statcan-wds", url="https://example", cached=False, schema_name="test"
)


@pytest.fixture
def wds(monkeypatch):
    calls: dict[str, list] = {"latest": [], "range": []}

    async def metadata_raw(pid):
        return _METADATA, True

    async def latest(pid, coordinates, latest_n):
        calls["latest"].append((pid, list(coordinates), latest_n))
        found = {
            "2.2": _series("2.2", 41690973, [_row(date(2026, 9, 1), 170.0)]),
            "3.2": _series("3.2", 41691244, [_row(date(2026, 9, 1), 168.0, status=1)]),
        }
        series = [found[c] for c in coordinates if c in found]
        first = series[0]
        return VectorData(
            **first.model_dump(),
            series=series if len(coordinates) > 1 else None,
            provenance=_PROVENANCE,
        )

    async def by_range(vector_ids, start, end):
        calls["range"].append((list(vector_ids), start, end))
        return VectorDataSet(
            series=[
                VectorSeries(
                    product_id=18100004,
                    coordinate="",
                    vector_id=v,
                    observations=[_row(date(2026, 1, 1), 165.0), _row(date(2026, 2, 1), 165.9)],
                )
                for v in vector_ids
            ],
            provenance=_PROVENANCE,
        )

    async def no_legend():
        return None

    monkeypatch.setattr(wds_client, "cube_metadata_raw", metadata_raw)
    monkeypatch.setattr(wds_client, "get_data_from_cube_pid_coords_and_latest_n_periods", latest)
    monkeypatch.setattr(wds_client, "get_data_from_vector_by_reference_period_range", by_range)
    monkeypatch.setattr(wds_client, "observation_legend", no_legend)
    return calls


async def test_latest_observations_come_from_wds(httpx_mock, cloudflare_challenge, wds):
    httpx_mock.add_response(url=f"{_DATA_URL}2.2?lastNObservations=1", **cloudflare_challenge)
    data = await client.get_data(18100004, "2.2", last_n_observations=1)
    assert wds["latest"] == [(18100004, ["2.2"], 1)]
    (series,) = data.series
    assert series.series_key == {"Geography": "2", "Products_and_product_groups": "2"}
    assert series.vector_id == 41690973 and series.uom_code == "17"
    assert [(o.period, o.value) for o in series.observations] == [("2026-09", 170.0)]
    # SDMX sends no attributes for a normal value, so neither does the fallback.
    assert series.observations[0].status_code is None
    assert data.provenance.source == "statcan-wds"
    assert "Cloudflare check" in (data.provenance.limits or "")


async def test_a_wildcard_takes_every_member_and_keeps_flags(httpx_mock, cloudflare_challenge, wds):
    httpx_mock.add_response(url=f"{_DATA_URL}.2?lastNObservations=1", **cloudflare_challenge)
    data = await client.get_data(18100004, ".2", last_n_observations=1)
    assert wds["latest"][0][1] == ["2.2", "3.2"]
    ontario = data.series[1]
    assert ontario.observations[0].status_code == 1
    assert ontario.observations[0].status == "use with caution"


async def test_a_period_range_reads_the_vectors_by_reference_period(
    httpx_mock, cloudflare_challenge, wds
):
    httpx_mock.add_response(
        url=f"{_DATA_URL}2.2?startPeriod=2026-01&endPeriod=2026-02", **cloudflare_challenge
    )
    data = await client.get_data(18100004, "2.2", start_period="2026-01", end_period="2026-02")
    assert wds["range"] == [([41690973], "2026-01-01", "2026-02-28")]
    assert [o.period for o in data.series[0].observations] == ["2026-01", "2026-02"]


async def test_a_key_too_wide_for_wds_names_the_dimension_to_narrow(
    httpx_mock, cloudflare_challenge, wds, monkeypatch
):
    many = {
        **_METADATA,
        "dimension": [
            {
                **_METADATA["dimension"][0],
                "member": [{"memberId": i} for i in range(1, 400)],
            },
            _METADATA["dimension"][1],
        ],
    }

    async def metadata_raw(pid):
        return many, True

    monkeypatch.setattr(wds_client, "cube_metadata_raw", metadata_raw)
    httpx_mock.add_response(url=f"{_DATA_URL}.2?lastNObservations=1", **cloudflare_challenge)
    with pytest.raises(InvalidInput, match=r"dimension 1 \(Geography, 399 members\)"):
        await client.get_data(18100004, ".2", last_n_observations=1)


async def test_a_key_with_the_wrong_number_of_segments_is_refused(
    httpx_mock, cloudflare_challenge, wds
):
    httpx_mock.add_response(url=f"{_DATA_URL}2?lastNObservations=1", **cloudflare_challenge)
    with pytest.raises(InvalidInput, match="needs 2 dot-separated segments"):
        await client.get_data(18100004, "2", last_n_observations=1)


async def test_the_structure_comes_from_wds_and_says_why(
    httpx_mock, cloudflare_challenge, monkeypatch
):
    httpx_mock.add_response(
        url=f"{constants.BASE_URL}structure/Data_Structure_18100004", **cloudflare_challenge
    )

    async def from_wds(product_id, lang):
        return [
            SdmxDimension(
                position=1,
                dimension_id="Geography",
                codelist_id="CL_Geography",
                codes=[SdmxCode(id="2", name_en="Canada", name_fr="Canada")],
            )
        ]

    monkeypatch.setattr(client, "_structure_from_wds", from_wds)
    structure = await client.get_structure(18100004)
    assert [d.dimension_id for d in structure.dimensions] == ["Geography"]
    assert "Web Data Service (WDS)" in (structure.provenance.coverage or "")
