"""Finding a StatCan table's copy and a series by its vector id (the WDS fallback's source).

Shaped like api.statcan.gc.ca on 2026-11-17: the "STC" v1.0 flows beside the production
"CA1.CCEI" v2.0 ones, the VECTOR attribute written "65201210" in one flow and "v2" in
another, and a whole-flow read that can be larger than the reader accepts.
"""

from __future__ import annotations

import pytest

from maplestats_mcp.modules.statcan.sdmx_spaces import client, constants
from maplestats_mcp.shared.errors import UpstreamError

CCEI = constants.SPACES["ccei"].base_url
SHARED = constants.SPACES["stcshared"].base_url


def _flow(agency: str, flow_id: str, version: str) -> dict:
    return {"id": flow_id, "version": version, "agencyID": agency, "name": flow_id}


def _list(httpx_mock, space: str, *flows: dict) -> None:
    httpx_mock.add_response(
        url=f"{space}/dataflow/all/all/latest", json={"data": {"dataflows": list(flows)}}
    )


HEADER = "STRUCTURE,STRUCTURE_ID,ACTION,FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE,VECTOR"


async def test_the_production_copy_is_found_and_the_reference_flow_is_not(httpx_mock):
    _list(
        httpx_mock,
        CCEI,
        _flow("STC", "DF_17100009", "1.0"),
        _flow("CA1.CCEI", "DF_17100009", "2.0"),
    )
    found = await client.find_table_flow(17100009)
    assert found == client.FlowRef("ccei", "CA1.CCEI", "DF_17100009", "2.0")
    assert found.ref == "CA1.CCEI,DF_17100009,2.0"


async def test_the_shared_space_is_searched_when_ccei_has_no_copy(httpx_mock):
    _list(httpx_mock, CCEI, _flow("CA1.CCEI", "DF_17100009", "2.0"))
    _list(httpx_mock, SHARED, _flow("CA1.QOL", "DF_11100090", "1.0"))
    found = await client.find_table_flow(11100090)
    assert found == client.FlowRef("stcshared", "CA1.QOL", "DF_11100090", "1.0")
    assert await client.find_table_flow(18100004) is None  # both lists are cached now


async def test_a_table_with_only_a_reference_flow_has_no_copy(httpx_mock):
    _list(httpx_mock, CCEI, _flow("STC", "DF_36100434", "1.0"))
    _list(httpx_mock, SHARED, _flow("CA1.QOL", "DF_11100090", "1.0"))
    assert await client.find_table_flow(36100434) is None


def test_vector_keys_read_both_spellings_and_drop_a_cut_row():
    # No final newline: the last row is cut off mid-transfer.
    text = (
        f"{HEADER}\n"
        "DATAFLOW,X,I,M,CA,2026-08,5,65201210\n"
        "DATAFLOW,X,I,M,ON,2026-08,6,v2\n"
        "DATAFLOW,X,I,M,BC,2026-08,7,\n"
        "DATAFLOW,X,I,M,AB,2026-08,8,65201211"
    )
    assert client._parse_vector_keys(text) == {65201210: "M.CA", 2: "M.ON"}
    assert client._parse_vector_keys(text + "\n") == {65201210: "M.CA", 2: "M.ON", 65201211: "M.AB"}


def test_a_flow_without_a_vector_column_or_not_sdmx_csv_gives_no_index():
    assert (
        client._parse_vector_keys("STRUCTURE,STRUCTURE_ID,ACTION,FREQ,OBS_VALUE\nD,X,I,M,1\n") == {}
    )
    assert client._parse_vector_keys("<html>challenge</html>\n") == {}
    assert client._parse_vector_keys("") == {}


async def test_vector_keys_are_one_cached_read_of_the_whole_flow(httpx_mock):
    flow = client.FlowRef("ccei", "CA1.CCEI", "DF_17100009", "2.0")
    httpx_mock.add_response(
        url=f"{CCEI}/data/CA1.CCEI,DF_17100009,2.0/all?lastNObservations=1",
        text=HEADER + "\nDATAFLOW,X,I,OD,CA,2026-07-01,41798407,v1\n",
    )
    assert await client.vector_keys(flow) == {1: "OD.CA"}
    assert await client.vector_keys(flow) == {1: "OD.CA"}  # no second request


async def test_a_flow_read_past_the_size_limit_is_not_indexed(httpx_mock, monkeypatch):
    monkeypatch.setattr(constants, "VECTOR_INDEX_MAX_BYTES", 100)
    flow = client.FlowRef("ccei", "CA1.CCEI", "DF_17100005", "2.0")
    httpx_mock.add_response(
        url=f"{CCEI}/data/CA1.CCEI,DF_17100005,2.0/all?lastNObservations=1",
        text=HEADER + "\n" + "DATAFLOW,X,I,A,CA,2026,1,v9\n" * 50,
    )
    with pytest.raises(UpstreamError, match="stops at 100"):
        await client.vector_keys(flow)


async def test_series_labels_name_members_in_key_order_without_the_frequency(httpx_mock):
    structure = {
        "data": {
            "dataflows": [
                {
                    **_flow("CA1.CCEI", "DF_17100009", "2.0"),
                    "description": "Population.<br/><strong>Release date:</strong> 2026-09-23",
                    "annotations": [{"type": "NonProductionDataflow", "text": "true"}],
                    "structure": "urn:sdmx:org.sdmx.infomodel.datastructure.DataStructure="
                    "CA1.CCEI:DSD_17100009(2.0)",
                }
            ],
            "dataStructures": [
                {
                    "id": "DSD_17100009",
                    "version": "2.0",
                    "agencyID": "CA1.CCEI",
                    "dataStructureComponents": {
                        "attributeList": {"attributes": []},
                        "dimensionList": {
                            "dimensions": [
                                {"id": "FREQ", "position": 0},
                                {
                                    "id": "REF_AREA",
                                    "position": 1,
                                    "localRepresentation": {
                                        "enumeration": "urn:sdmx:org.sdmx.infomodel.codelist."
                                        "Codelist=CA1:CL_AREA(1.0)"
                                    },
                                },
                            ],
                            "timeDimensions": [{"id": "TIME_PERIOD", "position": 2}],
                        },
                    },
                }
            ],
            "codelists": [
                {
                    "id": "CL_AREA",
                    "version": "1.0",
                    "agencyID": "CA1",
                    "codes": [{"id": "CA", "name": "Canada"}, {"id": "10", "name": "Alberta"}],
                }
            ],
            "contentConstraints": [],
        }
    }
    httpx_mock.add_response(
        url=f"{CCEI}/dataflow/CA1.CCEI/DF_17100009/2.0?references=all", json=structure
    )
    flow = client.FlowRef("ccei", "CA1.CCEI", "DF_17100009", "2.0")
    labels = await client.series_labels(flow, {"FREQ": "OD", "REF_AREA": "CA"}, "en")
    assert labels.members == [("REF_AREA", "Canada")]
    assert labels.release_date == "2026-09-23"
    assert labels.non_production is True
    assert labels.url == f"{CCEI}/dataflow/CA1.CCEI/DF_17100009/2.0"
