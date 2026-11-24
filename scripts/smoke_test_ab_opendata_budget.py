"""Live smoke test for ab_opendata_get_budget_table (Alberta fiscal plan tables).

Calls the client against open.alberta.ca; every request waits in the 10-second
bucket, so the run takes a few minutes. Expected values were read on 2026-11-24
from the downloaded Budget 2026 workbooks, cell by cell with openpyxl:
- Key Energy and Economic Assumptions: WTI US$60.50/bbl for 2026-27 (Forecast),
  three hidden columns (2017-18, 2019-20, 2020-21) whose cells read "#REF!".
- Total Revenue (Tb 1): 2026-27 Estimate $74,549.535 million; personal income
  tax $15,933.271 million.
- Summary Statement of Financial Position hides a stale "Budget" column.
- Budget 2025 (older dataset): WTI US$68 for 2025-26.
"""

from __future__ import annotations

import asyncio
import sys

from _smoke_common import skip_outage, verdict

from maplestats_mcp.modules.ab_opendata import client
from maplestats_mcp.shared.errors import InvalidInput
from maplestats_mcp.shared.http import new_client


async def main() -> int:
    failures = 0
    try:
        failures = await _checks()
    except Exception as exc:  # noqa: BLE001 - only an outage is skipped
        skip_outage("open.alberta.ca", exc)
    return verdict("AB OPENDATA BUDGET", not failures)


async def _checks() -> int:
    failures = 0

    def check(ok: bool, label: str) -> None:
        nonlocal failures
        print(("OK: " if ok else "FAIL: ") + label)
        failures += 0 if ok else 1

    async with new_client():
        parts = await client.get_budget_table()
        names = [p.part for p in parts.parts]
        check(
            parts.edition >= 2026 and {"economic outlook", "revenue", "other"} <= set(names),
            f"get_budget_table() -> Budget {parts.edition}: {names}",
        )
        check(parts.ogl_alberta and parts.attribution is not None, "fiscal plan under OGL-Alberta")

        outlook = await client.get_budget_table(part="economic outlook")
        check(
            any(s.table.lower().startswith("key") for s in outlook.tables)
            and not any(s.table == "Cover" for s in outlook.tables),
            f"economic outlook tables -> {len(outlook.tables)}, cover skipped",
        )

        key = await client.get_budget_table(
            part="economic outlook", table="Key Energy", edition=2026, contains="WTI"
        )
        wti = key.rows[0] if key.rows else None
        check(
            wti is not None and wti.values.get("2026-27 Forecast") == 60.5,
            f"Budget 2026 WTI 2026-27 -> {wti.values if wti else None}",
        )
        check(
            not any("#REF" in str(v) for r in key.rows for v in r.values.values()),
            "hidden #REF! columns left out",
        )

        revenue = await client.get_budget_table(part="revenue", table="Total Revenue", edition=2026)
        total = next((r for r in revenue.rows if (r.label or "").lower() == "total revenue"), None)
        check(
            total is not None and abs(float(total.values["2026-27 Estimate"]) - 74549.535) < 0.01,
            f"Total revenue 2026-27 -> {total.values if total else None}",
        )
        check(
            revenue.columns[:3] == ["2024-25 Actual", "2025-26 Budget", "2025-26 Forecast"],
            f"year spans two columns -> {revenue.columns}",
        )

        position = await client.get_budget_table(
            part="other", table="Summary Statement of Financial Position", edition=2026
        )
        check(
            not any("Budget" in c for c in position.columns),
            f"hidden Budget column left out -> {position.columns}",
        )

        older = await client.get_budget_table(
            edition=2025, part="economic outlook", table="Key Assumptions", contains="WTI"
        )
        check(
            older.edition == 2025
            and bool(older.rows)
            and older.rows[0].values.get("2025-26 Forecast") == 68,
            f"Budget 2025 WTI -> {older.rows[0].values if older.rows else None}",
        )

        try:
            await client.get_budget_table(part="nothing")
            check(False, "unknown part refused")
        except InvalidInput:
            check(True, "unknown part refused")

    return failures


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
