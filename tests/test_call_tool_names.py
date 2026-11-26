"""call_tool and tool names a client changed or misspelled (live /stats, 2026-11-06)."""

from __future__ import annotations

import pytest
from fastmcp import Client
from mcp.types import TextContent

from maplestats_mcp import server
from maplestats_mcp.server import _close_tool_names, _resolve_tool_name, mcp

CATALOG = ["wds_get_data_from_vectors", "wds_get_data_from_cube_coord", "boc_get_observations"]


def test_namespace_case_and_separators_resolve_to_the_tool() -> None:
    for name in (
        "maplestats.wds_get_data_from_vectors",
        "StatCan/wds_get_data_from_vectors",
        "maplestats:WDS_GET_DATA_FROM_VECTORS",
        "wds-get-data-from-vectors",
    ):
        assert _resolve_tool_name(name, CATALOG) == "wds_get_data_from_vectors", name


def test_a_misspelling_is_suggested_never_run() -> None:
    assert _resolve_tool_name("wds_get_data_from_vector", CATALOG) is None
    assert _close_tool_names("wds_get_data_from_vector", CATALOG)[0] == "wds_get_data_from_vectors"
    assert _close_tool_names("statcan_get_cpi", CATALOG) == []


def _text(result) -> str:
    first = result.content[0]
    assert isinstance(first, TextContent)
    return first.text


async def test_call_tool_runs_a_namespaced_name_and_suggests_for_a_typo() -> None:
    async with Client(mcp) as client:
        ran = await client.call_tool(
            "call_tool",
            {"name": "maplestats.plan_query_x", "arguments": {}},
            raise_on_error=False,
        )
        assert ran.is_error and "Unknown tool" in _text(ran)
        typo = await client.call_tool(
            "call_tool",
            {"name": "wds_get_data_from_vector", "arguments": {}},
            raise_on_error=False,
        )
        assert "Did you mean wds_get_data_from_vectors" in _text(typo)
        resolved = await client.call_tool(
            "call_tool",
            {"name": "maplestats.wds_get_data_from_vectors", "arguments": {}},
            raise_on_error=False,
        )
        # It reached the real tool, which asks for its required argument.
        assert "vector_ids is required" in _text(resolved)


@pytest.mark.parametrize(
    "name",
    ["wds_query_series", "maplestats.wds_query_series", "WDS_QUERY_SERIES", "wds-query-series"],
)
async def test_a_switched_off_tool_says_so_under_any_spelling_of_its_name(monkeypatch, name):
    # The switch was looked up by the raw name, so a namespaced or upper-case spelling of a
    # tool that is off got "Unknown tool" instead of the switched-off guidance.
    monkeypatch.setenv("MAPLE_QUERY_SERIES", "0")
    async with Client(server.build_server()) as client:
        ran = await client.call_tool(
            "call_tool", {"name": name, "arguments": {}}, raise_on_error=False
        )

    assert ran.is_error
    text = _text(ran)
    assert "wds_query_series is switched off on this server" in text
    assert "Unknown tool" not in text
