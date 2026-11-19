"""A WDS answer StatCan later blocks with its captcha is served from the last good copy.

StatCan put parts of www150 behind a Cloudflare check in November 2026, and two
outside projects saw WDS itself challenged overnight on 2026-11-17. The idea of
serving the last good copy, labelled, comes from vrraiv/sixfigures PR #105.
"""

from __future__ import annotations

import json

from fastmcp import Client
from mcp.types import TextContent

from maplestats_mcp.modules.statcan.wds import constants
from maplestats_mcp.server import mcp
from maplestats_mcp.shared import cache

_URL = f"{constants.BASE_URL}getCodeSets"


def _text(result) -> str:
    return next(b.text for b in result.content if isinstance(b, TextContent))


async def test_a_blocked_code_sets_refresh_is_served_from_the_last_good_copy(
    httpx_mock, cloudflare_challenge
):
    from maplestats_mcp.modules.statcan.wds.__tests__.conftest import CODE_SETS

    httpx_mock.add_response(url=_URL, json=CODE_SETS)
    async with Client(mcp) as client:
        first = await client.call_tool("wds_get_code_sets", {"category": "scalar"})
        assert "last good copy" not in _text(first)
        cache._caches.clear()  # the TTL ran out
        httpx_mock.add_response(url=_URL, **cloudflare_challenge)
        second = await client.call_tool("wds_get_code_sets", {"category": "scalar"})
    caveats = json.loads(_text(second))["provenance"]["caveats"]
    assert any("MapleStats' last good copy, fetched" in c for c in caveats)
