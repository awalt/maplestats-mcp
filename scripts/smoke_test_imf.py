"""Live smoke test for the imf module: calls the real IMF SDMX API (not mocks) for every
client function and every tool, per AGENTS.md's "lesson from auditing the StatCan module".

Exit status 75 (see _smoke_common) when api.imf.org is unreachable, challenged or answering
5xx; any other error fails the run.

Usage:
    uv run python scripts/smoke_test_imf.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from _smoke_common import skip_outage, verdict
from fastmcp import Client
from mcp.types import TextContent

from maplestats_mcp.modules.imf import client
from maplestats_mcp.server import mcp
from maplestats_mcp.shared.errors import InvalidInput, NotFound


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

    # 195 + 11 dataflows on 2026-11-18, 122 of them dated vintages.
    for query, expected, agency in (
        ("consumer price index", "CPI", "IMF.STA"),
        ("exchange rates", "ER", "IMF.STA"),
        ("balance of payments", "BOP", "IMF.STA"),
        ("labor statistics", "LS", "IMF.STA"),
        ("world economic outlook", "WEO", "IMF.RES"),
        ("primary commodity prices", "PCPS", "IMF.RES"),
    ):
        found = await client.search_datasets(query, limit=5)
        top = [(d.id, d.agency) for d in found.datasets]
        print(f"OK: search {query!r} -> {found.total_matches} matches, top {top[:3]}")
        if (expected, agency) not in top:
            print(f"FAIL: {expected} not in the top 5 for {query!r}")
            ok = False

    for dataset in ("CPI", "IMF.RES,WEO"):
        structure = await client.describe_dataset(dataset, lang="fr")
        print(
            f"OK: describe {dataset} -> {structure.key_template} e.g. {structure.example_key!r}, "
            f"{[d.total_codes for d in structure.dimensions]}"
        )
        ok &= all(d.codes for d in structure.dimensions) and structure.example_key.startswith("CAN")

    series = await client.search_series("CPI", query="all items index monthly")
    print(
        "OK: Canada CPI series ->",
        [(s.key, s.latest_period, s.latest_value) for s in series.series],
    )
    ok &= any(s.key == "CAN.CPI._T.IX.M" for s in series.series)

    cpi = await client.get_data("CPI", "CAN.CPI._T.IX.M", last_n=3)
    newest = cpi.rows[-1]
    print(f"OK: CPI -> {[(r.period, r.value) for r in cpi.rows]} (updated {cpi.provenance.as_of})")
    # The all-items index on Statistics Canada's own base: 170.0 for 2026-M09, 170.4 for
    # 2026-M10 on the Bank of Canada's V41690973 (the IMF runs about a month behind).
    ok &= cpi.series[0].frequency == "Monthly" and 160 < newest.value < 260
    ok &= newest.period >= "2026-M09" and cpi.provenance.commercial_use == "not_allowed"

    ranged = await client.get_data(
        "CPI", "CAN.CPI._T.IX.M", start_period="2026-M06", end_period="2026-M09"
    )
    print("OK: CPI June to September 2026 ->", [(r.period, r.value) for r in ranged.rows])
    ok &= [r.period for r in ranged.rows][:1] == ["2026-M06"]

    weo = await client.get_data("WEO", "CAN.NGDP_RPCH.A", last_n=6)
    print("OK: WEO real GDP growth ->", [(r.period, round(r.value, 2)) for r in weo.rows])
    ok &= len(weo.rows) == 6 and any("projections" in n for n in weo.notes)

    french = await client.search_series("WEO", query="gross domestic product", lang="fr")
    print(f"OK: WEO GDP series (fr) -> {french.total_matches}, {french.series[0].label[:80]}")
    ok &= french.total_matches >= 1 and "Canada" in french.series[0].label
    return ok


async def errors() -> bool:
    ok = True
    ok &= await _expect_error("unknown dataset", client.describe_dataset("NOPE"), NotFound)
    ok &= await _expect_error(
        "unknown country code", client.get_data("CPI", "ZZZ.CPI._T.IX.M", last_n=1), InvalidInput
    )
    ok &= await _expect_error("open key without periods", client.get_data("CPI", ""), InvalidInput)
    ok &= await _expect_error(
        "future period",
        client.get_data("CPI", "CAN.CPI._T.IX.M", start_period="2040"),
        NotFound,
    )
    return ok


async def through_server() -> bool:
    """Every tool once through call_tool, as a client reaches it (cached calls)."""
    ok = True
    calls = [
        ("imf_search_datasets", {"query": "consumer price index"}),
        ("imf_describe_dataset", {"dataset": "CPI"}),
        ("imf_search_series", {"dataset": "CPI", "query": "all items index monthly"}),
        ("imf_get_data", {"dataset": "CPI", "key": "CAN.CPI._T.IX.M", "last_n": 2}),
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
    return verdict("IMF", ok)


async def guarded() -> int:
    # An outage (a timeout, a Cloudflare challenge, a 5xx) skips the run; anything else fails it.
    try:
        return await run()
    except Exception as exc:  # noqa: BLE001
        skip_outage("api.imf.org", exc)
        return verdict("IMF", True)


if __name__ == "__main__":
    sys.exit(asyncio.run(guarded()))
