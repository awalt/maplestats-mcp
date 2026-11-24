"""Live smoke test for the Ontario Ministry of Finance population projections.

Calls every client function against data.ontario.ca. Expected values were read
on 2026-11-24 from the downloaded workbooks with openpyxl: Ontario 2025 base
population 16,258,260
(Summer 2026 release), 2026 base 16,262,121 in the Fall 2026 interim update;
Peel census division 1,632,557 in 2025; the 49 census divisions add up to the
Ontario total in the base year.
"""

from __future__ import annotations

import asyncio
import sys

from _smoke_common import skip_outage, verdict

from maplestats_mcp.modules.on_finance import client
from maplestats_mcp.shared.errors import InvalidInput
from maplestats_mcp.shared.http import new_client


async def main() -> int:
    failures = 0
    try:
        failures = await _checks()
    except Exception as exc:  # noqa: BLE001 - only an outage is skipped
        skip_outage("data.ontario.ca", exc)
    return verdict("ON FINANCE", not failures)


async def _checks() -> int:
    failures = 0

    def check(ok: bool, label: str) -> None:
        nonlocal failures
        print(("OK: " if ok else "FAIL: ") + label)
        failures += 0 if ok else 1

    async with new_client():
        latest = await client.get_population_projection(end_year=2051)
        check(
            latest.rows[0].year == latest.base_year and not latest.rows[0].projected,
            f"Ontario latest -> {latest.release}, base {latest.base_year}, "
            f"{latest.rows[0].total:,} to {latest.rows[-1].total:,} in {latest.rows[-1].year}",
        )
        annual = await client.get_population_projection(release="annual", scenario="any")
        base = [r for r in annual.rows if r.year == annual.base_year]
        check(
            not annual.interim
            and {r.scenario for r in annual.rows} == {"reference", "low", "high"}
            and len({r.total for r in base}) == 1,
            f"annual release -> {annual.release}; three scenarios share the base "
            f"{base[0].total if base else None}",
        )
        cds = await client.get_population_projection(
            geography="census_division", start_year=annual.base_year, end_year=annual.base_year
        )
        cd_sum = sum(r.total or 0 for r in cds.rows)
        check(
            len(cds.areas) == 49 and bool(base) and cd_sum == base[0].total,
            f"49 census divisions sum to {cd_sum:,} (Ontario {base[0].total if base else None})",
        )
        peel = await client.get_population_projection(
            geography="census_division", area="Peel", age_groups="single_year", end_year=2025
        )
        ages = peel.rows[0].ages or {} if peel.rows else {}
        check(
            bool(peel.rows) and sum(v or 0 for v in ages.values()) == peel.rows[0].total,
            f"Peel single years add to the total -> {peel.rows[0].total if peel.rows else None}",
        )
        phu = await client.get_population_projection(
            geography="public_health_unit", area="Toronto Public Health", start_year=2051
        )
        check(
            bool(phu.rows) and phu.rows[0].median_age is not None,
            f"Toronto PHU 2051 -> {phu.rows[0].total if phu.rows else None}, median age "
            f"{phu.rows[0].median_age if phu.rows else None}",
        )
        for geography in ("region", "mccss_region"):
            other = await client.get_population_projection(geography=geography, end_year=2025)
            check(
                bool(other.rows) and bool(other.areas), f"{geography} -> {len(other.areas)} areas"
            )

        components = await client.get_projection_components(scenario="any")
        first = components.rows[0] if components.rows else None
        check(
            first is not None
            and first.births is not None
            and first.start_population == latest.rows[0].total,
            f"components -> {components.release}, first period {first.period if first else None}",
        )
        try:
            await client.get_population_projection(geography="census_division", scenario="high")
            check(False, "sub-provincial high scenario refused")
        except InvalidInput:
            check(True, "sub-provincial high scenario refused")

    return failures


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
