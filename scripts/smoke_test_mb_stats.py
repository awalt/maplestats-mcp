"""Live smoke test for the Manitoba Bureau of Statistics module.

Calls every client function against www.gov.mb.ca/mbs. Expected values were read
on 2026-11-24 from the Bureau's CSV files and workbooks: about 60 indicator tiles (population
estimate 1,517,379 on July 1, 2026), 150 Excel data tables among 1,146 catalogue
rows, retail_mb.xlsx with a title row over a three-row header.
"""

from __future__ import annotations

import asyncio
import sys

from _smoke_common import skip_outage, verdict

from maplestats_mcp.modules.mb_stats import client
from maplestats_mcp.shared.errors import InvalidInput, NotFound
from maplestats_mcp.shared.http import new_client


async def main() -> int:
    failures = 0
    try:
        failures = await _checks()
    except Exception as exc:  # noqa: BLE001 - only an outage is skipped
        skip_outage("www.gov.mb.ca", exc)
    return verdict("MB STATS", not failures)


async def _checks() -> int:
    failures = 0

    def check(ok: bool, label: str) -> None:
        nonlocal failures
        print(("OK: " if ok else "FAIL: ") + label)
        failures += 0 if ok else 1

    async with new_client():
        indicators = await client.list_indicators()
        population = next((i for i in indicators.indicators if i.id == 16), None)
        check(
            len(indicators.indicators) >= 40 and population is not None and bool(population.value),
            f"list_indicators -> {len(indicators.indicators)}; population "
            f"{population.value if population else None} ({population.reference_period if population else None})",
        )
        check(
            all(i.title and i.category for i in indicators.indicators),
            "every indicator has a title and category (split summaries mended)",
        )
        files = await client.list_files(limit=200)
        check(
            files.total_files >= 100 and all(f.url.endswith(".xlsx") for f in files.files),
            f"list_files data tables -> {files.total_files}",
        )
        docs = await client.list_files(kind="document", query="weekly", limit=1)
        check(docs.total_files > 0, f"MBS Weekly bulletins -> {docs.total_files}")
        retail = await client.list_files(indicator=10)
        url = next((f.url for f in retail.files if f.url.endswith("/retail_mb.xlsx")), None)
        check(url is not None, f"retail indicator files -> {[f.url for f in retail.files]}")
        if url:
            table = await client.read_file(url=url, header_rows=3, contains="Retail trade")
            check(
                table.header_row == 2 and bool(table.rows) and table.rows[0][0] == "Retail trade",
                f"read_file retail_mb -> header row {table.header_row}, {table.header[:4]}",
            )
        try:
            await client.read_file(url="https://www.gov.mb.ca/mbs/publications/not_listed.xlsx")
            check(False, "unlisted file refused")
        except NotFound:
            check(True, "unlisted file refused")
        try:
            await client.read_file(url="https://example.com/mbs/publications/x.xlsx")
            check(False, "other host refused")
        except InvalidInput:
            check(True, "other host refused")

    return failures


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
