"""SERVER_INSTRUCTIONS must route every live tool by its name prefix.

The routing index is hand-written, so a new module whose prefix is not
added to it is invisible to a client that reads the instructions; four
live prefixes went missing that way before this check existed.

The index is checked under both GIS profiles (tests/gis_profiles.py): with MAPLE_GIS=0
the instructions the server sends name no prefix whose tools are all hidden.
"""

from __future__ import annotations

import re

import pytest

from maplestats_mcp import gis_profile
from maplestats_mcp.server import SERVER_INSTRUCTIONS
from tests.gis_profiles import PROFILES, STATS_ONLY, server_for

# Tools named in full in the instructions rather than by prefix.
_NAMED_IN_FULL = {"search_tools", "call_tool", "plan_query", "reproduce_code", "reproduce_workbook"}

_PREFIX_TOKEN = re.compile(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)*_)(?![a-z0-9])")
_NAME_TOKEN = re.compile(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b")


def _instructions(profile: str) -> str:
    """The text the server of `profile` sends to a client on initialize."""
    text = server_for(profile).instructions
    assert text is not None
    return text


def _listed_prefixes(profile: str) -> set[str]:
    return set(_PREFIX_TOKEN.findall(_instructions(profile)))


async def _tool_names(profile: str) -> set[str]:
    return {tool.name for tool in await server_for(profile)._list_tools()}


def test_the_default_profile_sends_the_instructions_unchanged():
    assert _instructions("default") == SERVER_INSTRUCTIONS


@pytest.mark.parametrize("profile", PROFILES)
async def test_every_live_tool_prefix_is_routed(profile: str):
    text = _instructions(profile)
    prefixes = _listed_prefixes(profile)
    names = await _tool_names(profile)
    unrouted = sorted(
        name
        for name in names
        if name not in _NAMED_IN_FULL
        and name not in text
        and not any(name.startswith(prefix) for prefix in prefixes)
    )
    assert not unrouted, (
        "Tools whose prefix is missing from SERVER_INSTRUCTIONS in server.py "
        f"(add the module's prefix to the routing index): {unrouted}"
    )


@pytest.mark.parametrize("profile", PROFILES)
async def test_every_listed_prefix_matches_a_live_tool(profile: str):
    names = await _tool_names(profile)
    stale = sorted(
        prefix
        for prefix in _listed_prefixes(profile)
        if not any(name.startswith(prefix) for name in names)
    )
    assert not stale, f"SERVER_INSTRUCTIONS lists prefixes with no live tool: {stale}"


@pytest.mark.parametrize("profile", PROFILES)
async def test_tool_names_written_in_full_exist(profile: str):
    names = await _tool_names(profile)
    prefixes = _listed_prefixes(profile)
    full_names = {
        token
        for token in _NAME_TOKEN.findall(_instructions(profile))
        if any(token.startswith(prefix) for prefix in prefixes)
    }
    missing = sorted(full_names - names)
    assert not missing, f"SERVER_INSTRUCTIONS names tools that do not exist: {missing}"


def test_stats_only_instructions_name_no_hidden_tool():
    text = _instructions(STATS_ONLY)
    for prefix in ("bcgw_", "eccc_coverages_", "nrcan_geo_", "nrcan_nbac_"):
        assert prefix not in text, prefix
    assert not any(tool in text for tool in gis_profile.PURE_GIS_TOOLS)
    # The prefixes that still have a tool in the profile stay named.
    for prefix in ("statcan_geo_", "cwfis_", "ab_wildfire_", "eccc_", "arcgis_hub_"):
        assert prefix in text, prefix


def test_stats_only_instructions_are_the_default_ones_less_the_cut_words():
    # Nothing else moves: the cut text is all that differs, and each cut matches once.
    text = SERVER_INSTRUCTIONS
    for cut in gis_profile.INSTRUCTION_CUTS:
        assert text.count(cut.start) == 1, f"{cut.start!r} no longer appears once"
        text = cut.apply(text)
    assert _instructions(STATS_ONLY) == text


@pytest.mark.parametrize("profile", PROFILES)
def test_portal_counts_are_not_hard_coded(profile: str):
    # Portal families grow by one constants entry at a time; a count in
    # this text goes stale on the next addition.
    assert not re.search(r"\(\d+ (provinces|portals|cities)", _instructions(profile))


def test_bug_report_requires_approval_before_filing():
    # The draft comes from the conversation, which can hold personal details,
    # so the client must show the final text and wait for the user's approval
    # before anything becomes a public GitHub issue.
    from maplestats_mcp.server import REPORT_ISSUE_TEMPLATE

    assert "Never file anything before the user approves" in SERVER_INSTRUCTIONS
    flat = " ".join(REPORT_ISSUE_TEMPLATE.split())
    assert "show the complete final title and body" in flat
    assert "STOP" in flat
    assert "File only after an explicit approval" in flat
    assert "redraft" in flat
    assert "Search open issues first" in flat
    assert "one report only" in flat
    assert "then file it" not in flat
