"""The `fred_` tools exist only while FRED_API_KEY holds a key.

FRED needs a free key that the server's operator creates (MapleStats never ships or asks for
one). With the variable unset or blank, the three tools leave `search_tools` and a module
that is nothing but those tools is not registered; a call by name says how to set the key.
With a key they are offered like any other tool (config.get_fred_enabled,
catalogue.TOOL_SWITCHES, the same mechanism that hides the pure geospatial class).
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from maplestats_mcp import config, server
from maplestats_mcp.catalogue import (
    FRED_TOOLS,
    PROFILE_SWITCHES,
    TOOL_SWITCHES,
    module_hidden,
    read_catalogue,
)

QUERY = "FRED St. Louis Fed series observations release dates"


async def _search(query: str = QUERY) -> str:
    async with Client(server.build_server()) as client:
        result = await client.call_tool("search_tools", {"query": query})
    return " ".join(getattr(part, "text", "") for part in result.content)


def test_the_three_tools_are_catalogued_and_switched_by_the_key():
    catalogue = read_catalogue() or {}
    listed = {tool["name"] for entry in catalogue.values() for tool in entry["tools"]}
    assert FRED_TOOLS == {"fred_search_series", "fred_get_series", "fred_get_release_dates"}
    assert FRED_TOOLS <= listed
    assert all(TOOL_SWITCHES[name] is config.get_fred_enabled for name in FRED_TOOLS)
    # A call by name gets FRED's own explanation, not the "unknown tool" a profile gives.
    assert not FRED_TOOLS & PROFILE_SWITCHES


@pytest.mark.parametrize("value", [None, "", "   "])
def test_an_unset_or_blank_key_switches_the_tools_off(monkeypatch: pytest.MonkeyPatch, value):
    if value is None:
        monkeypatch.delenv("FRED_API_KEY", raising=False)
    else:
        monkeypatch.setenv("FRED_API_KEY", value)
    assert config.get_fred_api_key() is None and config.get_fred_enabled() is False
    catalogue = read_catalogue() or {}
    assert module_hidden(catalogue["fred"]) is True


async def test_without_a_key_search_never_offers_a_fred_tool(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    assert "fred_" not in await _search()


async def test_a_call_by_name_says_how_to_set_the_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    async with Client(server.build_server()) as client:
        result = await client.call_tool(
            "call_tool",
            {"name": "fred_get_series", "arguments": {"series_id": "LRUNTTTTCAM156S"}},
            raise_on_error=False,
        )
    text = result.content[0].text  # type: ignore[union-attr]
    assert "FRED_API_KEY" in text and "never ships, asks for or stores a key" in text
    assert "https://fred.stlouisfed.org/docs/api/api_key.html" in text
    assert "Unknown tool" not in text


async def test_with_a_key_the_tools_are_offered(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FRED_API_KEY", "0123456789abcdef0123456789abcdef")
    assert config.get_fred_api_key() == "0123456789abcdef0123456789abcdef"
    assert module_hidden((read_catalogue() or {})["fred"]) is False
    text = await _search()
    assert "fred_search_series" in text
    # The key is never part of what a search returns.
    assert "0123456789abcdef0123456789abcdef" not in text


def test_the_catalogue_is_built_with_a_placeholder_key_that_is_not_left_behind():
    # The placeholder switches the tools on only while the catalogue is built.
    from maplestats_mcp import catalogue

    assert catalogue._SWITCH_ENV["FRED_API_KEY"] == "catalogue-build-placeholder"
    assert config.get_fred_api_key() != "catalogue-build-placeholder"
