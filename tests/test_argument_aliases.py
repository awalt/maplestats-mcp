"""call_tool reads a few commonly guessed argument names as the real ones (issue #273).

The unit tests cover the mapping rules; the call_tool tests run the real server with
each tool's client function replaced, so nothing reaches an upstream.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.tools import ToolResult
from mcp.types import TextContent

from maplestats_mcp.modules.boc import client as boc_client
from maplestats_mcp.modules.boc.schemas import ObservationsResult
from maplestats_mcp.modules.ckan import client as ckan_client
from maplestats_mcp.modules.ckan.schemas import PackageSearchResult
from maplestats_mcp.modules.jobbank import client as jobbank_client
from maplestats_mcp.modules.jobbank.schemas import OccupationWages, WageRelease
from maplestats_mcp.server import mcp, searchable_tools
from maplestats_mcp.shared.argument_aliases import ARGUMENT_ALIASES, Alias, apply_aliases
from maplestats_mcp.shared.envelope import make_provenance
from maplestats_mcp.shared.response_budget import add_caveats

BOC_PARAMETERS = {"series_names", "recent", "lang"}


def _provenance(lang: str = "en"):
    return make_provenance(
        source="test",
        url="https://example.test",
        cached=False,
        schema_name="test.Result",
        lang=lang,
    )


# --- The mapping rules ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "parameters", "arguments", "expected"),
    [
        (
            "boc_get_observations",
            BOC_PARAMETERS,
            {"series": "FXUSDCAD"},
            {"series_names": ["FXUSDCAD"]},
        ),
        (
            "boc_get_observations",
            BOC_PARAMETERS,
            {"series": ["FXUSDCAD", "FXEURCAD"], "recent": 5},
            {"series_names": ["FXUSDCAD", "FXEURCAD"], "recent": 5},
        ),
        ("jobbank_get_wages", {"noc", "region"}, {"noc_code": "72200"}, {"noc": "72200"}),
        (
            "ckan_search_datasets",
            {"portal", "rows"},
            {"portal": "federal", "limit": 5},
            {"portal": "federal", "rows": 5},
        ),
    ],
)
def test_each_alias_is_read_as_its_real_argument(tool, parameters, arguments, expected):
    mapped_arguments, mapped = apply_aliases(tool, parameters, arguments)
    assert mapped_arguments == expected
    assert [m.real for m in mapped] == [next(iter(set(expected) - set(arguments)))]


def test_a_single_string_is_wrapped_in_a_list_and_a_list_is_not():
    _, bare = apply_aliases("boc_get_observations", BOC_PARAMETERS, {"series": "FXUSDCAD"})
    _, listed = apply_aliases("boc_get_observations", BOC_PARAMETERS, {"series": ["FXUSDCAD"]})
    assert bare[0].wrapped is True
    assert listed[0].wrapped is False
    # Wrapping is for the list parameter only: a scalar one keeps what it was given.
    _, scalar = apply_aliases("jobbank_get_wages", {"noc"}, {"noc_code": "72200"})
    assert scalar[0].wrapped is False


def test_the_mapped_argument_keeps_the_aliases_position():
    mapped_arguments, _ = apply_aliases(
        "ckan_search_datasets",
        {"portal", "query", "rows"},
        {"portal": "on", "limit": 3, "query": "x"},
    )
    assert list(mapped_arguments or {}) == ["portal", "rows", "query"]


def test_the_alias_is_not_applied_when_the_real_name_is_also_given():
    arguments = {"series": "FXUSDCAD", "series_names": ["FXEURCAD"]}
    mapped_arguments, mapped = apply_aliases("boc_get_observations", BOC_PARAMETERS, arguments)
    assert mapped_arguments is arguments
    assert mapped == []
    # Not even when the caller's own value is null: it was supplied.
    nulled = {"limit": 5, "rows": None}
    assert apply_aliases("ckan_search_datasets", {"rows"}, nulled) == (nulled, [])


def test_a_tool_that_is_not_in_the_table_is_left_alone():
    arguments = {"series": "FXUSDCAD", "limit": 5, "noc_code": "72200"}
    for tool in ("wds_get_data_from_vectors", "boc_get_group_observations", "no_such_tool"):
        assert apply_aliases(tool, {"vector_ids"}, arguments) == (arguments, [])
    # An alias belongs to its own tool: `limit` is not read as `rows` on another one.
    assert apply_aliases("boc_get_observations", BOC_PARAMETERS, {"limit": 5}) == ({"limit": 5}, [])


def test_nothing_changes_for_no_arguments():
    assert apply_aliases("boc_get_observations", BOC_PARAMETERS, None) == (None, [])
    assert apply_aliases("boc_get_observations", BOC_PARAMETERS, {}) == ({}, [])


def test_a_real_parameter_is_never_shadowed_by_an_alias():
    # If a tool gains a parameter named like its alias, the alias stops applying.
    arguments = {"limit": 5}
    assert apply_aliases("ckan_search_datasets", {"rows", "limit"}, arguments) == (arguments, [])
    # And an alias whose real argument the tool no longer has is not mapped either.
    assert apply_aliases("ckan_search_datasets", {"portal"}, arguments) == (arguments, [])


def test_the_note_names_both_arguments_in_english_and_french():
    _, mapped = apply_aliases("boc_get_observations", BOC_PARAMETERS, {"series": "FXUSDCAD"})
    english = mapped[0].note("en")
    french = mapped[0].note("fr")
    assert "`series` was read as `series_names`" in english
    assert "single value was put in a list" in english
    assert "`series` a été lu comme `series_names`" in french
    assert "valeur unique" in french


async def test_the_table_matches_the_tools_it_names():
    tools = {t.name: t for t in await searchable_tools(mcp)}
    for tool, aliases in ARGUMENT_ALIASES.items():
        assert tool in tools, f"{tool} is not a tool of this server"
        properties = set(tools[tool].parameters.get("properties", {}))
        assert len({spec.real for spec in aliases.values()}) == len(aliases), tool
        for alias, spec in aliases.items():
            assert alias not in properties, f"{tool} has its own `{alias}` parameter"
            assert spec.real in properties, f"{tool} has no `{spec.real}` parameter"
    # The table is the three guesses issue #273 measured, nothing wider.
    assert ARGUMENT_ALIASES == {
        "boc_get_observations": {"series": Alias("series_names", as_list=True)},
        "jobbank_get_wages": {"noc_code": Alias("noc")},
        "ckan_search_datasets": {"limit": Alias("rows")},
    }


# --- add_caveats ---------------------------------------------------------------------


def _result(payload: dict[str, Any]) -> ToolResult:
    return ToolResult(
        content=[TextContent(type="text", text=json.dumps(payload))], structured_content=payload
    )


def test_add_caveats_appends_after_the_existing_ones_and_rewrites_the_text():
    result = _result({"provenance": {"caveats": ["first"]}})
    noted = add_caveats(result, ["second", "first"])
    assert noted.structured_content == {"provenance": {"caveats": ["first", "second"]}}
    assert json.loads(noted.content[0].text) == noted.structured_content  # type: ignore[union-attr]


def test_add_caveats_starts_the_list_when_provenance_has_none():
    noted = add_caveats(_result({"provenance": {"source": "x"}}), ["note"])
    assert noted.structured_content == {"provenance": {"source": "x", "caveats": ["note"]}}


def test_add_caveats_leaves_a_result_without_a_provenance_block_alone():
    result = _result({"rows": []})
    assert add_caveats(result, ["note"]) is result
    assert add_caveats(_result({"provenance": {}}), []) is not None


# --- call_tool -----------------------------------------------------------------------


@pytest.fixture
def seen(monkeypatch) -> dict[str, dict[str, Any]]:
    """The arguments each replaced client function was called with, by tool."""
    calls: dict[str, dict[str, Any]] = {}

    async def get_observations(series_names, **kwargs):
        calls["boc_get_observations"] = {"series_names": series_names, **kwargs}
        return ObservationsResult(
            series={}, observations=[], provenance=_provenance(kwargs.get("lang", "en"))
        )

    async def get_wages(noc, region, province, published_only, release_year, lang):
        calls["jobbank_get_wages"] = {"noc": noc, "region": region, "lang": lang}
        return OccupationWages(
            noc_code=noc,
            occupation="Electricians",
            rows=[],
            returned_count=0,
            published_count=0,
            unpublished_count=0,
            release=WageRelease(
                release_year=2025,
                resource_id="r",
                dataset_url="https://example.test/d",
                job_bank_url="https://example.test/j",
                methodology_url="https://example.test/m",
                citation="Job Bank, 2025",
                available_years=[2025],
            ),
            provenance=_provenance(lang),
        )

    async def search_datasets(portal, query="", *, rows=10, lang="en", **kwargs):
        calls["ckan_search_datasets"] = {"portal": portal, "rows": rows, "lang": lang}
        return PackageSearchResult(
            portal=portal,
            packages=[],
            total_count=0,
            returned_count=0,
            start=0,
            rows=rows,
            query=query,
            provenance=_provenance(lang),
        )

    monkeypatch.setattr(boc_client, "get_observations", get_observations)
    monkeypatch.setattr(jobbank_client, "get_wages", get_wages)
    monkeypatch.setattr(ckan_client, "search_datasets", search_datasets)
    return calls


async def _run(name: str, arguments: dict[str, Any], **extra: Any):
    async with Client(mcp) as client:
        return await client.call_tool(
            "call_tool", {"name": name, "arguments": arguments, **extra}, raise_on_error=False
        )


def _body(result: Any) -> dict[str, Any]:
    block = result.content[0]
    assert isinstance(block, TextContent)
    return json.loads(block.text)


@pytest.mark.parametrize(
    ("name", "arguments", "reached", "alias", "real"),
    [
        (
            "boc_get_observations",
            {"series": "FXUSDCAD", "recent": 5},
            {"series_names": ["FXUSDCAD"], "recent": 5},
            "series",
            "series_names",
        ),
        (
            "boc_get_observations",
            {"series": ["FXUSDCAD", "FXEURCAD"]},
            {"series_names": ["FXUSDCAD", "FXEURCAD"]},
            "series",
            "series_names",
        ),
        ("jobbank_get_wages", {"noc_code": "72200"}, {"noc": "72200"}, "noc_code", "noc"),
        (
            "ckan_search_datasets",
            {"portal": "federal", "limit": 7},
            {"portal": "federal", "rows": 7},
            "limit",
            "rows",
        ),
    ],
)
@pytest.mark.parametrize("detail", [None, "full"])
async def test_a_guessed_name_runs_the_tool_and_the_result_says_so(
    seen, name, arguments, reached, alias, real, detail
):
    extra = {} if detail is None else {"detail": detail}
    result = await _run(name, arguments, **extra)
    assert not result.is_error
    for key, value in reached.items():
        assert seen[name][key] == value
    caveats = _body(result)["provenance"]["caveats"]
    assert any(f"`{alias}` was read as `{real}`" in note for note in caveats), caveats
    # The structured content carries the same note as the text.
    assert result.structured_content is not None
    assert result.structured_content["provenance"]["caveats"] == caveats


async def test_the_note_is_in_french_for_a_french_call(seen):
    result = await _run("ckan_search_datasets", {"portal": "federal", "limit": 3, "lang": "fr"})
    assert not result.is_error
    assert seen["ckan_search_datasets"]["rows"] == 3
    caveats = _body(result)["provenance"]["caveats"]
    assert any("a été lu comme `rows`" in note for note in caveats), caveats


async def test_the_real_name_gets_no_note(seen):
    result = await _run("ckan_search_datasets", {"portal": "federal", "rows": 7})
    assert not result.is_error
    caveats = _body(result)["provenance"].get("caveats", [])
    assert not any("was read as" in note for note in caveats)


async def test_both_names_are_not_mapped_and_validation_speaks(seen):
    result = await _run(
        "boc_get_observations", {"series": "FXUSDCAD", "series_names": ["FXEURCAD"]}
    )
    assert result.is_error
    text = _body_text(result)
    assert text.startswith("[invalid_input] Invalid input: boc_get_observations: ")
    assert "series is not a parameter of this tool" in text
    assert "boc_get_observations" not in seen


async def test_an_alias_of_another_tool_still_fails_as_before(seen):
    # `limit` is ckan_search_datasets' alias, not jobbank_get_wages': nothing is read.
    result = await _run("jobbank_get_wages", {"noc": "72200", "limit": 5})
    assert result.is_error
    assert "limit is not a parameter of this tool" in _body_text(result)
    # And a tool outside the table gets the same error it always did.
    other = await _run("wds_get_data_from_vectors", {"series": "v1"})
    assert other.is_error
    text = _body_text(other)
    assert text.startswith("[invalid_input] Invalid input: wds_get_data_from_vectors: ")
    assert "series is not a parameter of this tool" in text
    assert seen == {}


async def test_the_alias_is_read_only_through_call_tool(seen):
    # A tool called by its own name keeps its published signature.
    async with Client(mcp) as client:
        result = await client.call_tool(
            "boc_get_observations", {"series": "FXUSDCAD"}, raise_on_error=False
        )
    assert result.is_error
    assert "series is not a parameter of this tool" in _body_text(result)
    assert seen == {}


def _body_text(result: Any) -> str:
    block = result.content[0]
    assert isinstance(block, TextContent)
    return block.text
