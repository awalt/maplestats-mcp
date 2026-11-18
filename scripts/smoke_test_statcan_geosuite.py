"""Live smoke test for statcan_geosuite_: the real re-host at data.mountainmath.ca (not
mocks), every client function and every tool, per AGENTS.md's "lesson from auditing the
StatCan module".

It reads all six manifests, downloads a handful of tables (2016 CSD, DA and DB, 1996 EA,
2021 CSD and PR, about 10 MB in all) into the GeoSuite cache folder, and checks values
against the 2016 census's published counts (Canada 35,151,728; Toronto 2,731,571).

Usage:
    uv run python scripts/smoke_test_statcan_geosuite.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

from fastmcp import Client
from mcp.types import TextContent

from maplestats_mcp.modules.statcan.geosuite import client, constants
from maplestats_mcp.server import mcp
from maplestats_mcp.shared.errors import InvalidInput


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
    listing = None
    for year in constants.YEARS:
        listing = await client.list_tables(year)
        names = [t.table for t in listing.tables]
        print(
            f"OK: list_tables({year}) -> {len(names)} tables, built {listing.build_date}, "
            f"sources {[s.file for s in listing.sources]}"
        )
        ok &= len(names) >= 21 and "CSD" in names and "PR" in names
        ok &= bool(listing.provenance.caveats) and "re-host" in listing.provenance.caveats[0]
    if listing is not None:
        print("   caveat:", listing.provenance.caveats[0][:300])
        print("   licence:", listing.provenance.licence)

    t0 = time.monotonic()
    pr = await client.query(2016, "PR", columns=["PRUID", "PRNAME", "PRFNAME", "PRPOP2016"])
    total = sum(int(r["PRPOP2016"] or 0) for r in pr.rows)
    print(f"OK: 2016 PR -> {pr.total_matched} rows, population sum {total:,}")
    ok &= pr.total_matched == 13 and total == 35151728

    toronto = await client.query(2016, "CSD", filters={"CSDUID": ["3520005"]})
    row = toronto.rows[0]
    print(
        "OK: 2016 Toronto ->",
        {k: row[k] for k in ("CSDNAME", "CSDTYPE", "CSDPOP2016", "CSDAREA2016", "CMAUID")},
        f"({time.monotonic() - t0:.1f} s)",
    )
    ok &= row["CSDPOP2016"] == 2731571 and row["CMAUID"] == "535"

    ontario = await client.query(
        2016, "CSD", filters={"PRUID": ["35"]}, columns=["CSDUID", "CSDNAME"], limit=3
    )
    print(f"OK: 2016 Ontario CSDs -> {ontario.total_matched}, first {ontario.rows}")
    ok &= ontario.total_matched == 575 and ontario.truncated

    montreal = await client.query(
        2016, "CSD", name_contains="montreal", columns=["CSDUID", "CSDNAME"], lang="fr"
    )
    print(
        "OK: name_contains montreal ->",
        [r["CSDNAME"] for r in montreal.rows],
        "|",
        montreal.provenance.coverage,
    )
    ok &= any(r["CSDUID"] == "2466023" for r in montreal.rows)

    t0 = time.monotonic()
    da = await client.query(2016, "DA", filters={"DAUID": ["35204831"]})
    blocks = await client.query(2016, "DB", filters={"DBUID": ["35204831*"]})
    block_pop = sum(int(r["DBPOP2016"] or 0) for r in blocks.rows)
    print(
        f"OK: 2016 DA 35204831 -> pop {da.rows[0]['DAPOP2016']}, {blocks.total_matched} blocks "
        f"summing to {block_pop} ({time.monotonic() - t0:.1f} s incl. DA and DB downloads)"
    )
    ok &= da.total_matched == 1 and block_pop == da.rows[0]["DAPOP2016"]

    ea = await client.query(1996, "EA", filters={"PRUID": ["35"]}, limit=1)
    print(f"OK: 1996 Ontario EAs -> {ea.total_matched}")
    ok &= ea.total_matched > 10000
    print("   1996 caveat:", ea.provenance.caveats[0][-160:])

    quebec = await client.query(2021, "CSD", name_contains="québec", columns=["CSDUID", "CSDNAME"])
    print("OK: 2021 québec ->", [r["CSDNAME"] for r in quebec.rows])
    ok &= any(r["CSDUID"] == "2423027" for r in quebec.rows)

    described = await client.describe_table(2016, "CSD")
    sample = described.sample_rows[0]
    print(
        f"OK: describe 2016 CSD -> {len(described.columns)} columns, key "
        f"{described.primary_key}, name columns {described.name_columns}, "
        f"first {sample['CSDUID']} {sample['CSDNAME']}"
    )
    ok &= len(described.columns) == 30 and described.columns[0].label is not None
    ok &= described.source_check is not None and described.source_check.identical_columns == 30
    print("   check:", described.provenance.caveats[1][:200])

    french = await client.describe_table(2021, "PR", lang="fr")
    print(f"OK: describe 2021 PR (fr) -> {french.title}; {french.columns[1].label}")
    ok &= french.title.startswith("Recensement de 2021")
    return ok


async def errors() -> bool:
    ok = True
    ok &= await _expect_error("unknown year", client.list_tables(2019), InvalidInput)
    ok &= await _expect_error("unknown table", client.query(2016, "EA"), InvalidInput)
    ok &= await _expect_error(
        "unknown column", client.query(2016, "DB", filters={"DAUID": ["35204831"]}), InvalidInput
    )
    ok &= await _expect_error("limit too high", client.query(2016, "CSD", limit=5000), InvalidInput)
    ok &= await _expect_error(
        "no name column", client.query(2016, "ADA", name_contains="x"), InvalidInput
    )
    return ok


async def through_server() -> bool:
    """Every tool once through call_tool, as a client reaches it."""
    ok = True
    calls = [
        ("statcan_geosuite_list_tables", {"year": 2016, "lang": "fr"}),
        ("statcan_geosuite_describe_table", {"year": 2011, "table": "CT"}),
        (
            "statcan_geosuite_query",
            {"year": 2016, "table": "CMA_CA", "name_contains": "ottawa", "limit": 5},
        ),
    ]
    async with Client(mcp) as session:
        for name, args in calls:
            result = await session.call_tool("call_tool", {"name": name, "arguments": args})
            text = next(c.text for c in result.content if isinstance(c, TextContent))
            if result.is_error:
                print(f"FAIL: call_tool({name}) -> {text[:300]}")
                ok = False
                continue
            data = json.loads(text)
            print(f"OK: call_tool({name}) -> {sorted(data)[:6]}")
    return ok


async def run() -> int:
    print(f"cache: {constants.cache_dir()} ({constants.BASE_URL})")
    ok = await main()
    ok &= await errors()
    ok &= await through_server()
    print("ALL OK" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
