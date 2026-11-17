"""The MAPLE_GIS profile: the class map, the default that changes nothing, and the
statistics-only profile that hides the PURE geospatial tools everywhere.

What the profile promises (maplestats_mcp/gis_profile.py, docs/ROADMAP.md "GIS tools"):
with the variable unset the server is exactly what it was; with MAPLE_GIS=0 the 14 PURE
tools are absent from search_tools, plan_query, the instructions, docs://catalogue and
call_tool, a call by name reads as any unknown tool, a module that is nothing but PURE
tools is not registered, and the 40 HYBRID tools stay. The discovery, planner and
instruction tests run under both profiles too (tests/gis_profiles.py).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import textwrap

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import NotFoundError, ToolError
from mcp.shared.exceptions import MCPError

from maplestats_mcp import config, gis_profile, server
from maplestats_mcp.catalogue import (
    PROFILE_SWITCHES,
    TOOL_SWITCHES,
    module_hidden,
    read_catalogue,
)
from maplestats_mcp.gis_profile import HYBRID_GIS_TOOLS, PURE_GIS_TOOLS
from maplestats_mcp.modules.planner import client as planner
from maplestats_mcp.modules.planner.topics import TOPICS
from tests.discovery_benchmark.runner import load_queries
from tests.gis_profiles import DEFAULT, STATS_ONLY, profile_env, server_for

# Modules that are nothing but PURE tools: not registered at all under MAPLE_GIS=0.
WHOLLY_PURE_MODULES = {"bcgw", "nrcan_geo", "nrcan_nbac"}
# Where the GIS-class tools live, as the catalogue names a tool's module. A tool added
# to one of them has to be classified (PURE or HYBRID) before the suite passes.
GIS_MODULE_PREFIXES = (
    "ab_wildfire.",
    "arcgis_hub.",
    "bcgw.",
    "cwfis.",
    "drivebc.",
    "earthquakes.",
    "eccc.",
    "eps.",
    "ised.spectrum.",
    "nrcan_geo.",
    "nrcan_nbac.",
    "statcan.geo.",
    "statcan.lode.",
)
# Names the PURE class leaves nowhere in text: the full tool names, and the prefixes no
# HYBRID tool shares (`statcan_geo_`, `cwfis_` and `ab_wildfire_` stay in use).
PURE_ONLY_PREFIXES = ("bcgw_", "eccc_coverages_", "nrcan_geo_", "nrcan_nbac_")
_HIDDEN_NAMES = "|".join(sorted(map(re.escape, PURE_GIS_TOOLS), key=len, reverse=True))
HIDDEN_NAME = re.compile(
    rf"(?<![a-z0-9_])(?:(?:{_HIDDEN_NAMES})(?![a-z0-9_])|{'|'.join(PURE_ONLY_PREFIXES)})"
)


def _catalogue_tools() -> dict[str, dict]:
    catalogue = read_catalogue()
    assert catalogue is not None
    return {tool["name"]: tool for entry in catalogue.values() for tool in entry["tools"]}


def _leaks(text: str) -> list[str]:
    return sorted(set(HIDDEN_NAME.findall(text)))


async def _page(source: FastMCP, uri: str) -> str:
    """The text a server serves at a docs:// uri."""
    content = (await source.read_resource(uri)).contents[0].content
    assert isinstance(content, str), uri
    return content


# The class map ---------------------------------------------------------------------------


def test_every_class_name_is_a_catalogued_tool():
    names = set(_catalogue_tools())
    assert PURE_GIS_TOOLS <= names, sorted(PURE_GIS_TOOLS - names)
    assert HYBRID_GIS_TOOLS <= names, sorted(HYBRID_GIS_TOOLS - names)


def test_the_two_classes_do_not_overlap():
    assert not PURE_GIS_TOOLS & HYBRID_GIS_TOOLS


def test_every_tool_of_a_gis_module_is_classified():
    unclassified = sorted(
        name
        for name, tool in _catalogue_tools().items()
        if tool["module"].startswith(GIS_MODULE_PREFIXES)
        and name not in PURE_GIS_TOOLS | HYBRID_GIS_TOOLS
    )
    assert not unclassified, (
        f"classify {unclassified} as PURE or HYBRID in maplestats_mcp/gis_profile.py"
    )


def test_a_classified_tool_lives_in_a_gis_module():
    tools = _catalogue_tools()
    strays = sorted(
        name
        for name in PURE_GIS_TOOLS | HYBRID_GIS_TOOLS
        if not tools[name]["module"].startswith(GIS_MODULE_PREFIXES)
    )
    assert not strays, f"add the module of {strays} to GIS_MODULE_PREFIXES"


def test_the_switch_hides_the_pure_class_and_only_it():
    switched = {name for name, switch in TOOL_SWITCHES.items() if switch is config.get_gis_enabled}
    assert switched == PURE_GIS_TOOLS == set(PROFILE_SWITCHES)
    assert not switched & HYBRID_GIS_TOOLS


def test_only_the_wholly_pure_modules_are_hidden_whole():
    catalogue = read_catalogue()
    assert catalogue is not None
    with profile_env(STATS_ONLY):
        hidden = {name for name, entry in catalogue.items() if module_hidden(entry)}
    assert hidden == WHOLLY_PURE_MODULES
    with profile_env(DEFAULT):
        assert not any(module_hidden(entry) for entry in catalogue.values())


# The default changes nothing --------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "1", "true", "yes", "on", "", "  ", "anything else"])
def test_the_variable_is_on_unless_it_says_off(monkeypatch: pytest.MonkeyPatch, value: str | None):
    if value is None:
        monkeypatch.delenv("MAPLE_GIS", raising=False)
    else:
        monkeypatch.setenv("MAPLE_GIS", value)
    assert config.get_gis_enabled() is True
    assert gis_profile.hidden_tools() == frozenset()


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off", " Off "])
def test_the_variable_turns_the_profile_on_when_it_says_off(
    monkeypatch: pytest.MonkeyPatch, value: str
):
    monkeypatch.setenv("MAPLE_GIS", value)
    assert config.get_gis_enabled() is False
    assert gis_profile.hidden_tools() == PURE_GIS_TOOLS


def test_the_default_profile_cuts_no_text():
    with profile_env(DEFAULT):
        sample = "bcgw_ (BC Geographic\n  Warehouse), eccc_coverages_ (from nrcan_geo_locate)"
        cuts = gis_profile.INSTRUCTION_CUTS
        assert gis_profile.cut_text(sample, cuts) is sample
        assert gis_profile.without_pointers(sample) is sample
        assert not gis_profile.names_hidden_tool(sample)


async def test_the_default_server_lists_every_tool_and_both_classes():
    names = {tool.name for tool in await server_for(DEFAULT)._list_tools()}
    assert names == set(_catalogue_tools())
    assert PURE_GIS_TOOLS | HYBRID_GIS_TOOLS <= names
    providers = [
        p for p in server_for(DEFAULT).providers if isinstance(p, server.LazyModuleProvider)
    ]
    assert WHOLLY_PURE_MODULES <= {p._root.name for p in providers}


async def test_the_default_server_sends_every_text_whole():
    default = server_for(DEFAULT)
    assert default.instructions == server.SERVER_INSTRUCTIONS
    text = await _page(default, "docs://catalogue")
    for module in WHOLLY_PURE_MODULES:
        assert f"\n## {module}\n" in text, module
    assert "eccc_coverages_ tools read" in text
    assert "statcan_geo_list_services finds" in text
    assert "perimeters" in text


# The words that are cut ---------------------------------------------------------------------


def _description(module: str, lang: str) -> str:
    import importlib

    attribute = "MODULE_DESCRIPTION" if lang == "en" else "MODULE_DESCRIPTION_FR"
    return getattr(importlib.import_module(f"maplestats_mcp.modules.{module}"), attribute)


@pytest.mark.parametrize(("module", "lang"), sorted(gis_profile.DESCRIPTION_CUTS))
def test_each_description_cut_matches_once_and_leaves_no_hidden_name(module: str, lang: str):
    text = _description(module, lang)
    for cut in gis_profile.DESCRIPTION_CUTS[(module, lang)]:
        assert text.count(cut.start) == 1, f"{module} {lang}: {cut.start!r}"
        assert cut.end is None or cut.end in text[text.index(cut.start) :], cut.end
        text = cut.apply(text)
    assert not _leaks(text), (module, lang, _leaks(text))


@pytest.mark.parametrize("name", sorted(gis_profile.TOOL_DESCRIPTION_CUTS))
def test_each_tool_listing_cut_matches_once_and_leaves_no_hidden_name(name: str):
    text = _catalogue_tools()[name]["description"]
    for cut in gis_profile.TOOL_DESCRIPTION_CUTS[name]:
        assert text.count(cut.start) == 1, f"{name}: {cut.start!r}"
        text = cut.apply(text)
    assert not _leaks(text), name


@pytest.mark.parametrize("uri", sorted(gis_profile.RESOURCE_CUTS))
async def test_each_resource_cut_matches_once_and_leaves_no_hidden_name(uri: str):
    text = await _page(server_for(DEFAULT), uri)
    for cut in gis_profile.RESOURCE_CUTS[uri]:
        assert text.count(cut.start) == 1, f"{uri}: {cut.start!r}"
        text = cut.apply(text)
    assert not _leaks(text), uri


def test_a_cut_removes_from_start_through_end_and_ignores_a_missing_one():
    cut = gis_profile.Cut("[", "]")
    assert cut.apply("a [b] c") == "a  c"
    assert cut.apply("a [b c") == "a [b c"
    assert gis_profile.Cut("x").apply("axb") == "ab"
    assert gis_profile.Cut("zz").apply("axb") == "axb"


def test_pointers_and_mentions_follow_the_profile(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MAPLE_GIS", "0")
    english = "latitude, longitude (from nrcan_geo_locate)"
    french = "latitude, longitude (tirées de nrcan_geo_locate)"
    assert gis_profile.without_pointers(english) == "latitude, longitude"
    assert gis_profile.without_pointers(french) == "latitude, longitude"
    # Only a parenthesis that names a hidden tool goes; a tool still offered stays.
    assert gis_profile.without_pointers("a (see eccc_query_items)") == "a (see eccc_query_items)"
    assert gis_profile.names_hidden_tool("Use nrcan_geo_locate to place it.")
    assert not gis_profile.names_hidden_tool("Use nrcan_geo_locate_more_often.")
    assert not gis_profile.names_hidden_tool("Use eccc_query_items.")


# The statistics-only profile ----------------------------------------------------------------


@pytest.fixture(scope="module")
def stats_only():
    with profile_env(STATS_ONLY):
        yield server_for(STATS_ONLY)


async def _search(stats_server, query: str) -> list[str]:
    async with Client(stats_server) as client:
        result = await client.call_tool("search_tools", {"query": query})
    return [item["name"] for item in (result.structured_content or {}).get("result", [])]


async def test_the_pure_class_is_not_listed_and_the_rest_is(stats_only):
    names = {tool.name for tool in await stats_only._list_tools()}
    assert not names & PURE_GIS_TOOLS
    assert HYBRID_GIS_TOOLS <= names
    assert names == set(_catalogue_tools()) - PURE_GIS_TOOLS


async def test_a_wholly_pure_module_has_no_provider(stats_only):
    registered = {p._root.name for p in stats_only.providers if hasattr(p, "_root")}
    assert not registered & WHOLLY_PURE_MODULES
    # Mixed modules stay: their HYBRID tools do.
    assert {"eccc", "statcan", "cwfis", "ab_wildfire"} <= registered


async def test_search_never_returns_a_hidden_tool_and_still_finds_the_hybrids(stats_only):
    async with Client(stats_only) as client:
        for name in sorted(PURE_GIS_TOOLS | HYBRID_GIS_TOOLS):
            result = await client.call_tool("search_tools", {"query": name})
            found = [item["name"] for item in (result.structured_content or {}).get("result", [])]
            if name in PURE_GIS_TOOLS:
                assert name not in found, name
            else:
                assert found[:1] == [name], (name, found)


async def test_call_tool_reads_a_hidden_name_as_any_unknown_tool(stats_only):
    async with Client(stats_only) as client:
        for name in sorted(PURE_GIS_TOOLS):
            result = await client.call_tool(
                "call_tool", {"name": name, "arguments": {}}, raise_on_error=False
            )
            text = result.content[0].text  # type: ignore[union-attr]
            assert result.is_error, name
            assert f"Unknown tool: '{name}'" in text, (name, text)
            assert "switched off" not in text, name
        # The tool is not there to resolve by name either, whatever the wrapper says.
        with pytest.raises(NotFoundError):
            await stats_only.call_tool("bcgw_query_layer", {})
        with pytest.raises(NotFoundError):
            await stats_only.call_tool("statcan_geo_query_layer", {})


async def test_call_tool_still_reaches_a_hybrid(stats_only):
    async with Client(stats_only) as client:
        result = await client.call_tool(
            "call_tool",
            {"name": "eps_get_last_load_date", "arguments": {"bogus": 1}},
            raise_on_error=False,
        )
    # The tool's own argument error, not "unknown tool".
    assert "Unknown tool" not in result.content[0].text  # type: ignore[union-attr]


async def test_the_other_switches_keep_their_own_error_text(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MAPLE_PUMF_TABULATE", "0")
    built = server.build_server()
    async with Client(built) as client:
        result = await client.call_tool(
            "call_tool", {"name": "statcan_pumf_tabulate", "arguments": {}}, raise_on_error=False
        )
    assert "switched off on this server" in result.content[0].text  # type: ignore[union-attr]


async def test_the_instructions_and_the_module_page_name_no_hidden_tool(stats_only):
    assert not _leaks(stats_only.instructions or "")
    text = await _page(stats_only, "docs://catalogue")
    assert not _leaks(text), _leaks(text)
    for module in WHOLLY_PURE_MODULES:
        assert f"\n## {module}\n" not in text, module
    # The page lists a module per registered folder: the default's 90, less the three.
    assert text.count("\n## ") == len(read_catalogue() or {}) - len(WHOLLY_PURE_MODULES)


async def _prompt_text(client: Client, prompt) -> str:
    required = {a.name: "1" for a in (prompt.arguments or []) if a.required}
    try:
        got = await client.get_prompt(prompt.name, required)
    except (ToolError, MCPError):
        # An argument that needs a real value (an integer): no text is served for "1".
        return ""
    return " ".join(getattr(m.content, "text", "") for m in got.messages)


async def test_nothing_the_stats_only_server_shows_names_a_hidden_tool(stats_only):
    """Listings, instructions, every docs:// page and every prompt: the scan the cuts came from."""
    leaks: dict[str, list[str]] = {}
    for tool in await stats_only._list_tools():
        found = _leaks(json.dumps(tool.to_mcp_tool().model_dump(mode="json"), ensure_ascii=False))
        if found:
            leaks[f"tool {tool.name}"] = found
    async with Client(stats_only) as client:
        for resource in await client.list_resources():
            body = await client.read_resource(str(resource.uri))
            found = _leaks(" ".join(getattr(part, "text", "") or "" for part in body))
            if found:
                leaks[f"resource {resource.uri}"] = found
        for prompt in await client.list_prompts():
            found = _leaks(await _prompt_text(client, prompt))
            if found:
                leaks[f"prompt {prompt.name}"] = found
    assert not leaks, leaks


async def test_the_eager_listing_equals_the_lazy_one_under_the_profile(stats_only):
    """A module the catalogue lacks loads eagerly; it honours the switch as the lazy one does."""
    eager = {}
    with profile_env(STATS_ONLY):
        for root in server.module_dirs():
            for tool in await server.ModuleProvider(root=root)._list_tools():
                eager[tool.name] = tool.description
    lazy = {tool.name: tool.description for tool in await stats_only._list_tools()}
    assert eager == lazy


# The planner under the profile --------------------------------------------------------------


def _plan_tools_and_text(plan) -> tuple[list[str], str]:
    steps = [
        *(s for t in plan.topics for s in t.steps),
        *(s for p in plan.places for s in p.steps),
        *plan.fallback_steps,
    ]
    text = " ".join(
        [
            *(s.purpose for s in steps),
            *(c for t in plan.topics for c in t.caveats),
            *plan.guidance,
        ]
    )
    return [s.tool for s in steps], text


def _benchmark_plans(profile: str):
    with profile_env(profile):
        return [(q.id, _plan_tools_and_text(planner.plan(q.query, q.lang))) for q in load_queries()]


def test_the_default_plans_do_name_pure_tools():
    # The sweep below proves nothing unless some plan would have named one.
    named = [qid for qid, (tools, _) in _benchmark_plans(DEFAULT) if set(tools) & PURE_GIS_TOOLS]
    assert len(named) >= 10, named


def test_a_hidden_tool_is_never_planned():
    """Every benchmark question, English and French: no step, purpose or caveat names one."""
    dangling = {}
    for qid, (tools, text) in _benchmark_plans(STATS_ONLY):
        found = sorted(set(tools) & PURE_GIS_TOOLS) + _leaks(text)
        if found:
            dangling[qid] = found
    assert not dangling, dangling


def test_every_topic_and_place_plans_without_a_hidden_tool():
    """Each topic's own terms (so every topic is asked for), and every place alias."""
    from maplestats_mcp.modules.planner.places import CITIES, PROVINCES

    dangling = {}
    with profile_env(STATS_ONLY):
        questions = [topic.terms[0].rstrip("*") for topic in TOPICS if topic.terms]
        questions += [f"data for {alias}" for alias in (*CITIES, *PROVINCES)]
        for question in questions:
            tools, text = _plan_tools_and_text(planner.plan(question))
            found = sorted(set(tools) & PURE_GIS_TOOLS) + _leaks(text)
            if found:
                dangling[question] = found
    assert not dangling, dangling


def test_a_topic_whose_steps_are_all_hidden_is_not_matched():
    with profile_env(DEFAULT):
        shown = planner.plan("coordinates of a place").topics
    with profile_env(STATS_ONLY):
        hidden = planner.plan("coordinates of a place").topics
    assert [t.topic for t in shown] == ["places"]
    assert [s.tool for s in shown[0].steps] == ["nrcan_geo_locate", "nrcan_geo_search_names"]
    assert not hidden


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_the_words_that_point_at_a_hidden_tool_leave_the_plan(lang: str):
    question = "Alberta wildfire danger rating and fire ban near Hinton"
    with profile_env(DEFAULT):
        shown = planner.plan(question, lang)
    with profile_env(STATS_ONLY):
        hidden = planner.plan(question, lang)
    shown_text = " ".join(
        [s.purpose for t in shown.topics for s in t.steps]
        + [c for t in shown.topics for c in t.caveats]
    )
    assert "nrcan_geo_locate" in shown_text
    hidden_steps = [s for t in hidden.topics for s in t.steps]
    assert "ab_wildfire_get_fire_danger" in [s.tool for s in hidden_steps]
    purpose = next(s.purpose for s in hidden_steps if s.tool == "ab_wildfire_get_fire_danger")
    assert "nrcan_geo" not in purpose and purpose.rstrip().endswith("longitude")
    assert "nrcan_geo_locate" not in _plan_tools_and_text(hidden)[1]


# A fresh interpreter ------------------------------------------------------------------------

_FRESH = textwrap.dedent(
    """
    import asyncio, json, sys

    from maplestats_mcp import server

    async def main():
        await server.preload(server.mcp)
        folders = {root.name for root in server.module_dirs()}
        imported = {
            name.split(".")[0] for name in sys.modules if name.split(".")[0] in folders
        } | {
            name.split(".")[2]
            for name in sys.modules
            if name.startswith("maplestats_mcp.modules.") and name.count(".") >= 2
        }
        lazy = {tool.name for tool in await server.mcp._list_tools()}
        eager = set()
        for root in server.module_dirs():
            eager |= {tool.name for tool in await server.ModuleProvider(root=root)._list_tools()}
        print(json.dumps({
            "imported": sorted(imported & {"bcgw", "nrcan_geo", "nrcan_nbac"}),
            "loaded_boc": "boc" in imported,
            "only_lazy": sorted(lazy - eager),
            "only_eager": sorted(eager - lazy),
            "tools": len(lazy),
        }))

    asyncio.run(main())
    """
)


def _fresh(env_value: str | None) -> dict:
    import os

    env = {**os.environ, "MAPLE_TRANSPORT": "stdio"}
    env.pop("MAPLE_GIS", None)
    if env_value is not None:
        env["MAPLE_GIS"] = env_value
    done = subprocess.run(
        [sys.executable, "-c", _FRESH],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=900,
        check=False,
    )
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_preload_skips_the_wholly_pure_modules_under_the_profile():
    """Preload imports every registered module; the three PURE-only ones are not registered."""
    off = _fresh("0")
    assert off["imported"] == []
    assert off["loaded_boc"] is True
    assert off["only_lazy"] == [] and off["only_eager"] == []
    on = _fresh(None)
    assert on["imported"] == ["bcgw", "nrcan_geo", "nrcan_nbac"]
    assert on["tools"] - off["tools"] == len(PURE_GIS_TOOLS)
