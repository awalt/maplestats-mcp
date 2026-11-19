"""Live smoke test for the fred module: calls the real FRED API (not mocks) for every client
function and every tool, per AGENTS.md's "lesson from auditing the StatCan module".

FRED needs a free API key that the person running this creates (MapleStats never ships or
asks for one), read from FRED_API_KEY. Without it the run is skipped with exit status 75
(see _smoke_common), as for an outage: not a failure of the code, not a pass either. The
module was written from FRED's documentation without a key, so the first run with one is
the first time any of it meets the real API: read every FAIL.

Usage:
    FRED_API_KEY=<your key> uv run python scripts/smoke_test_fred.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from _smoke_common import SKIPPED_EXIT, skip_outage, verdict
from fastmcp import Client
from mcp.types import TextContent

from maplestats_mcp.modules.fred import client
from maplestats_mcp.server import mcp
from maplestats_mcp.shared.errors import InvalidInput, NotFound

# The Canadian unemployment series the research of 2026-11-17 read through FRED's graph file
# (OECD-sourced, Oct 2026 = 6.7, the same as Statistics Canada's seasonally adjusted rate).
UNEMPLOYMENT = "LRUNTTTTCAM156S"


async def _expect_error(label: str, coro, exc_type: type[Exception]) -> bool:
    try:
        await coro
    except exc_type as exc:
        print(f"OK: {label} -> {type(exc).__name__}: {str(exc)[:140]}")
        return True
    except Exception as exc:  # noqa: BLE001 - smoke test wants to see everything
        print(f"FAIL: {label} -> {type(exc).__name__}: {exc}")
        return False
    print(f"FAIL: {label} -> no error")
    return False


async def main() -> bool:
    ok = True
    found = await client.search_series("Canada unemployment rate", limit=10)
    print(
        f"OK: search -> {found.total_matches} matches, top {[s.series_id for s in found.series[:5]]}"
    )
    ok &= len(found.series) >= 1 and found.series[0].page_url.startswith("https://fred.stlouisfed")

    series = await client.get_series(UNEMPLOYMENT, last_n=3)
    print(
        f"OK: {UNEMPLOYMENT} -> {series.title[:60]} | withheld={series.values_withheld} | "
        f"{[(o.date, o.value) for o in series.observations]}"
    )
    # An OECD series FRED marks Copyright is described, not read; either answer is correct.
    ok &= series.values_withheld or len(series.observations) == 3
    ok &= "not endorsed or certified" in (series.provenance.licence or "")
    ok &= "YOUR_FRED_API_KEY" in series.provenance.url

    key = os.environ.get("FRED_API_KEY", "")
    ok &= key not in json.dumps(series.model_dump(), default=str)

    dates = await client.get_release_dates(UNEMPLOYMENT, limit=5)
    print(f"OK: release {dates.release_name} -> {dates.dates}, upcoming {dates.upcoming}")
    ok &= len(dates.dates) >= 1

    french = await client.search_series("chômage Canada", limit=3, lang="fr")
    print(f"OK: search (fr) -> {[s.series_id for s in french.series]}")
    ok &= any("FRED" in n or "Fed" in n for n in french.notes)
    return ok


async def errors() -> bool:
    ok = True
    ok &= await _expect_error("unknown series", client.get_series("NOSUCHSERIES1"), NotFound)
    ok &= await _expect_error("bad series id", client.get_series("not a series"), InvalidInput)
    ok &= await _expect_error(
        "bad date", client.get_series(UNEMPLOYMENT, start_date="last year"), InvalidInput
    )
    return ok


async def through_server() -> bool:
    """Every tool once through call_tool, as a client reaches it (cached calls)."""
    ok = True
    calls = [
        ("fred_search_series", {"query": "Canada unemployment rate"}),
        ("fred_get_series", {"series_id": UNEMPLOYMENT, "last_n": 2}),
        ("fred_get_release_dates", {"series_id": UNEMPLOYMENT, "limit": 3}),
    ]
    async with Client(mcp) as session:
        for name, args in calls:
            result = await session.call_tool("call_tool", {"name": name, "arguments": args})
            text = next(c.text for c in result.content if isinstance(c, TextContent))
            data = json.loads(text)
            print(f"OK: call_tool({name}) -> {sorted(data)[:6]}")
            ok &= not result.is_error
    return ok


async def run() -> int:
    ok = await main()
    ok &= await errors()
    ok &= await through_server()
    return verdict("FRED", ok)


async def guarded() -> int:
    if not os.environ.get("FRED_API_KEY", "").strip():
        print("SKIP: FRED_API_KEY is not set (create a free key at FRED and export it)")
        return SKIPPED_EXIT
    try:
        return await run()
    except Exception as exc:  # noqa: BLE001
        skip_outage("api.stlouisfed.org", exc)
        return verdict("FRED", True)


if __name__ == "__main__":
    sys.exit(asyncio.run(guarded()))
