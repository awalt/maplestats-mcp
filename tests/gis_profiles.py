"""The two profiles the discovery, planner and instruction tests run under.

`default` is the server as it ships: every tool. `stats_only` is the same code with
MAPLE_GIS=0, which hides the PURE geospatial class (maplestats_mcp/gis_profile.py). A
test that names a tool the profile hides does not skip: it asserts the tool is absent, so
the switch is held to what it promises, and every other case keeps its real check.

The server reads MAPLE_GIS twice: while it is built (the tools its providers list, its
instructions) and on each call (the planner's steps, `call_tool`'s unknown-name text).
`server_for` builds each profile once, and `profile_env` holds the variable for the calls.
"""

from __future__ import annotations

import functools
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastmcp import FastMCP

from maplestats_mcp import gis_profile

DEFAULT = "default"
STATS_ONLY = "stats_only"
PROFILES = (DEFAULT, STATS_ONLY)


@contextmanager
def profile_env(profile: str) -> Iterator[None]:
    """MAPLE_GIS as the profile sets it, for the length of the block (the default unsets it)."""
    with pytest.MonkeyPatch.context() as patch:
        if profile == STATS_ONLY:
            patch.setenv("MAPLE_GIS", "0")
        else:
            patch.delenv("MAPLE_GIS", raising=False)
        yield


@functools.cache
def server_for(profile: str) -> FastMCP:
    """The shipped server for `default`; a second one, built with MAPLE_GIS=0, for `stats_only`."""
    # Imported here: the profile fixture lives in tests/conftest.py, which every run loads,
    # and importing the server builds it (several seconds) for tests that never ask.
    from maplestats_mcp import server

    if profile == DEFAULT:
        return server.mcp
    with profile_env(profile):
        return server.build_server()


def hides(profile: str, tool: str) -> bool:
    """Whether `profile` hides `tool`."""
    return profile == STATS_ONLY and tool in gis_profile.PURE_GIS_TOOLS
