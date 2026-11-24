"""Live smoke test for the Saskatchewan Bureau of Statistics module.

Calls every client function against publications.saskatchewan.ca. Expected values were
read on 2026-11-24: eight products, "SPEA Tables" (format 153159, posted 2026-01-19) with
an index sheet and table sheets 1.1 on, Compensation of Employees on sheet 1.1, and a
2016 census workbook in the legacy .xls format (format 100724).
"""

from __future__ import annotations

import asyncio
import sys

from _smoke_common import skip_outage, verdict

from maplestats_mcp.modules.sk_stats import client
from maplestats_mcp.shared.errors import InvalidInput
from maplestats_mcp.shared.http import new_client


async def main() -> int:
    failures = 0
    try:
        failures = await _checks()
    except Exception as exc:  # noqa: BLE001 - only an outage is skipped
        skip_outage("publications.saskatchewan.ca", exc)
    return verdict("SK STATS", not failures)


async def _checks() -> int:
    failures = 0

    def check(ok: bool, label: str) -> None:
        nonlocal failures
        print(("OK: " if ok else "FAIL: ") + label)
        failures += 0 if ok else 1

    async with new_client():
        tables = await client.list_files(limit=200)
        check(
            tables.total_files >= 20 and all(f.kind == "data_table" for f in tables.files),
            f"list_files Excel tables -> {tables.total_files}",
        )
        docs = await client.list_files(product="labour_force", kind="document", limit=5)
        check(docs.total_files >= 10, f"labour force PDF reports -> {docs.total_files}")
        accounts = await client.list_files(product="economic_accounts", query="tables")
        spea = next((f for f in accounts.files if f.title == "SPEA Tables"), None)
        check(spea is not None, f"SPEA Tables listed -> {[f.title for f in accounts.files]}")
        if spea:
            sheets = await client.read_file(spea.format_id)
            names = [s.name for s in sheets.sheets]
            check("index" in names and "1.1" in names, f"SPEA sheets -> {names[:6]}")
            table = await client.read_file(
                spea.format_id, sheet="1.1", contains="Compensation of Employees"
            )
            check(
                bool(table.rows) and table.header_row is not None,
                f"sheet 1.1 -> header row {table.header_row}, {table.all_columns[-3:]}",
            )
            check(
                table.provenance.commercial_use == "not_allowed",
                f"commercial_use -> {table.provenance.commercial_use}",
            )
        census = await client.read_file(100724)
        check(
            census.format == "xls" and census.total_rows > 100,
            f"2016 census .xls -> {census.format}, {census.total_rows} rows",
        )
        try:
            await client.read_file(docs.files[0].format_id)
            check(False, "PDF refused")
        except InvalidInput:
            check(True, "PDF refused")

    return failures


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
