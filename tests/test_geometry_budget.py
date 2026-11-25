"""The response budget never cuts a polygon: it drops whole rows instead.

arcgis_hub_query_feature_layer(return_geometry=True) puts each row's Esri JSON geometry
under `_geometry` (a row's own fields may be called `geometry`). `trim_payload` kept
`geometry`, `coordinates`, `geometries` and `bbox` whole but not `_geometry`, so a result
over MAPLE_RESPONSE_MAX_BYTES had its rings cut on real layers (checked live on
2026-11-17 against Ontario GeoHub, Manitoba and Niagara Region layers): first each
vertex [x, y] lost its y, then each ring was cut to a prefix, an open ring that is no
longer a shape. Dropping whole rows keeps every returned polygon true, and the note in
`provenance.limits` says rows were dropped.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.tools import ToolResult
from mcp.types import TextContent

from maplestats_mcp.server import mcp
from maplestats_mcp.shared.limits import (
    DEFAULT_MAX_BYTES,
    json_size,
    response_max_bytes,
    trim_payload,
)
from maplestats_mcp.shared.models import Provenance
from maplestats_mcp.shared.response_budget import apply_budget

BUDGET = 200_000


def _ring(vertices: int, seed: int) -> list[list[float]]:
    """A closed ring of Esri JSON [x, y] vertices, coordinates as long as a service sends them."""
    rng = random.Random(seed)
    ring = [
        [round(-90.0 + rng.random(), 7), round(48.0 + rng.random(), 7)] for _ in range(vertices - 1)
    ]
    return [*ring, ring[0]]


def _row(object_id: int, vertices: int) -> dict[str, Any]:
    return {
        "OBJECTID": object_id,
        "NAME": f"Polygon {object_id}",
        "_geometry": {
            "rings": [_ring(vertices, object_id)],
            "spatialReference": {"wkid": 4326, "latestWkid": 4326},
        },
    }


def _payload(rows: int, vertices: int) -> dict[str, Any]:
    """The shape of FeatureQueryResult in arcgis_hub, which `call_tool` budgets."""
    return {
        "portal": "ottawa",
        "item_id": "0123456789abcdef0123456789abcdef",
        "layer_index": 0,
        "rows": [_row(i, vertices) for i in range(rows)],
        "returned_count": rows,
        "limit": rows,
        "offset": 0,
        "where": "1=1",
        "exceeded_transfer_limit": False,
        "provenance": Provenance(
            source="arcgis-hub-ottawa",
            url="https://example.org/FeatureServer/0/query",
            queried_at=datetime(2026, 11, 17, tzinfo=UTC),
            cached=False,
            schema_name="arcgis_hub.FeatureQueryResult",
            limits="rows capped at 1000 per request",
        ).model_dump(mode="json"),
    }


def _assert_whole_polygons(rows: list[dict[str, Any]], vertices: int) -> None:
    """Every polygon that came back is the one the service sent."""
    for row in rows:
        (ring,) = row["_geometry"]["rings"]
        assert ring == _ring(vertices, row["OBJECTID"]), row["OBJECTID"]
        assert all(len(vertex) == 2 for vertex in ring)
        assert ring[0] == ring[-1]


def test_the_budget_is_still_200_000_bytes():
    # The fix is in what is trimmed, never in how much may be sent.
    assert DEFAULT_MAX_BYTES == BUDGET
    assert response_max_bytes() == BUDGET


def test_rows_with_geometry_are_dropped_whole_not_cut():
    payload = _payload(rows=40, vertices=3_000)
    assert json_size(payload) > 10 * BUDGET
    trimmed = trim_payload(payload, BUDGET)
    kept = payload["rows"]
    assert 0 < len(kept) < 40
    assert [kept_row["OBJECTID"] for kept_row in kept] == list(range(len(kept)))  # a prefix
    _assert_whole_polygons(kept, 3_000)
    assert json_size(payload) <= BUDGET
    assert payload["returned_count"] == len(kept)
    # One group was trimmed: the rows, not the vertices inside them.
    assert [(t.pattern, t.kept, t.total) for t in trimmed] == [("rows", len(kept), 40)]


def test_paths_and_points_are_whole_too():
    # Lines and points sit under the same key (Esri JSON `paths` and `points`).
    rows = [{"OBJECTID": i, "_geometry": {"paths": [_ring(3_000, i)]}} for i in range(30)] + [
        {"OBJECTID": 99, "_geometry": {"points": _ring(3_000, 99)}}
    ]
    payload = {"rows": rows, "returned_count": len(rows)}
    trim_payload(payload, BUDGET)
    for row in payload["rows"]:
        geometry = row["_geometry"]
        line = geometry.get("paths", [geometry.get("points")])[0]
        assert len(line) == 3_000 and all(len(vertex) == 2 for vertex in line)


def test_a_row_that_fits_the_budget_is_untouched():
    payload = _payload(rows=3, vertices=200)
    before = json.dumps(payload)
    assert trim_payload(payload, BUDGET) == []
    assert json.dumps(payload) == before


def test_one_polygon_over_the_budget_still_comes_back_whole():
    # fit_to_budget always keeps one row, so an answer is never empty. The polygon is
    # not cut to fit: `geometry` has always been returned whole when it is the only row.
    payload = _payload(rows=1, vertices=60_000)
    assert json_size(payload) > 5 * BUDGET
    assert trim_payload(payload, BUDGET) == []
    _assert_whole_polygons(payload["rows"], 60_000)


def test_the_note_says_rows_were_dropped_not_vertices():
    payload = _payload(rows=40, vertices=3_000)
    result = ToolResult(
        content=[TextContent(type="text", text=json.dumps(payload))], structured_content=payload
    )
    out = apply_budget(result, "arcgis_hub_query_feature_layer", {"lang": "en"}, BUDGET)
    body = out.structured_content
    assert body is not None
    kept = len(body["rows"])
    limits = body["provenance"]["limits"]
    assert limits.startswith("rows capped at 1000 per request. Trimmed to fit")
    assert f"kept the first {kept} of 40 items in `rows`" in limits
    assert "_geometry" not in limits and "rings" not in limits
    assert len(out.content[0].text.encode()) <= BUDGET  # type: ignore[union-attr]
    _assert_whole_polygons(body["rows"], 3_000)
    french = apply_budget(
        ToolResult(
            content=[TextContent(type="text", text=json.dumps(_payload(40, 3_000)))],
            structured_content=_payload(40, 3_000),
        ),
        "arcgis_hub_query_feature_layer",
        {"lang": "fr"},
        BUDGET,
    )
    assert (
        f"les {kept} premiers éléments sur 40 de `rows`"
        in (
            french.structured_content["provenance"]["limits"]  # type: ignore[index]
        )
    )


# Through the server, with the layer's answer mocked ----------------------------------------

ITEM_ID = "14cca5b087f74d2d9eadc018c261d1b3"
SERVICE = "https://services.arcgis.com/G6F8XLCl5KtAlZ2G/arcgis/rest/services/Parks/FeatureServer"
COLLECTION = "https://open.ottawa.ca/api/search/v1/collections/all"


@pytest.mark.parametrize("detail", ["full", None])
async def test_the_tool_returns_whole_polygons_through_call_tool(httpx_mock, detail):
    """The real client and the real middleware: rows are dropped, each polygon is intact."""
    vertices, asked = 2_000, 12
    httpx_mock.add_response(
        url=f"{COLLECTION}/items/{ITEM_ID}",
        json={
            "id": f"{ITEM_ID}_0",
            "type": "Feature",
            "geometry": None,
            "properties": {
                "id": ITEM_ID,
                "title": "Parks",
                "type": "Feature Service",
                "url": SERVICE,
            },
        },
    )
    httpx_mock.add_response(url=f"{SERVICE}?f=json", json={"layers": [{"id": 0}], "tables": []})
    features = [
        {
            "attributes": {"OBJECTID": i, "NAME": f"Polygon {i}"},
            "geometry": {"rings": [_ring(vertices, i)], "spatialReference": {"wkid": 4326}},
        }
        for i in range(asked)
    ]
    httpx_mock.add_response(
        url=(
            f"{SERVICE}/0/query?where=1%3D1&outFields=%2A&f=json&resultRecordCount={asked}"
            "&resultOffset=0&returnGeometry=true"
        ),
        json={"features": features, "exceededTransferLimit": False},
    )
    arguments = {
        "name": "arcgis_hub_query_feature_layer",
        "arguments": {
            "portal": "ottawa",
            "item_id": ITEM_ID,
            "return_geometry": True,
            "limit": asked,
        },
    }
    if detail is not None:
        arguments["detail"] = detail
    async with Client(mcp) as client:
        result = await client.call_tool("call_tool", arguments)
    text = result.content[0].text  # type: ignore[union-attr]
    assert len(text.encode()) <= BUDGET
    # Brief or full, the text is what a client reads: whole polygons, fewer rows.
    body = json.loads(text)
    _assert_whole_polygons(body["rows"], vertices)
    assert body["returned_count"] == len(body["rows"]) < asked
    limits = body["provenance"]["limits"]
    assert f"of {asked} items in `rows`" in limits
    assert "_geometry" not in limits
