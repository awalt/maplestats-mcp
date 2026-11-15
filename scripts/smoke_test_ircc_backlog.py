"""Live smoke test for IRCC's inventories-and-backlogs page (ircc_backlog_).

uv run python scripts/smoke_test_ircc_backlog.py
"""

from __future__ import annotations

import asyncio
import sys

from _smoke_common import skip_outage

from maplestats_mcp.modules.ircc.backlog import client
from maplestats_mcp.shared.errors import InvalidInput, UpstreamError, UpstreamUnavailable


async def main() -> int:
    ok = True
    try:
        # Checked 2026-11-14: seven programs, January 2022 to November 2025,
        # last actual month September 2025 in every table.
        everything = await client.get_backlog()
        print(
            f"OK: {len(everything.programs)} programs, {everything.returned_count} rows; "
            f"last actual months: {sorted({str(p.last_actual_month) for p in everything.programs})}"
        )
        ok &= len(everything.programs) == 7 and everything.returned_count >= 7 * 40

        # Express Entry federal, January 2022: IRCC's table shows 89% actual.
        ee = await client.get_backlog("express_entry_federal", since="2022-01", until="2022-01")
        row = ee.rows[0]
        print(f"OK: express_entry_federal 2022-01 -> actual {row.backlog_actual_pct}%")
        ok &= row.backlog_actual_pct == 89.0 and row.backlog_projected_pct is None

        french = await client.get_backlog("permis de travail", since="2022-01", lang="fr")
        ok &= french.programs[0].program_id == "work_permit" and len(french.rows) >= 40
        print(f"OK: FR work permits -> {french.programs[0].label}, {len(french.rows)} rows")

        try:
            await client.get_backlog("zzz")
            print("FAIL: unknown program did not raise")
            ok = False
        except InvalidInput:
            print("OK: unknown program -> InvalidInput")
    except (UpstreamUnavailable, UpstreamError) as exc:
        skip_outage("canada.ca", exc)

    print("\nIRCC BACKLOG SMOKE TEST PASSED" if ok else "\nIRCC BACKLOG SMOKE TEST FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
