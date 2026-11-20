"""Live smoke test for the Treasury Board and Finance tools of the Open Alberta reader.

Calls every TBF client function against open.alberta.ca. Every request waits
in the 10-second bucket, so the run takes a few minutes. Checked by hand on
2026-11-19:
- Alberta Activity Index: 548 months, January 1981 (100.0) to August 2026
  (327.7); series "Alberta Activity Index (January 1981 = 100)".
- 2026-2051 projections: Alberta medium scenario 6,959,145 in 2051 (All);
  census division 4806 (Calgary) sheet; CMA sheets Calgary, Edmonton,
  Lethbridge, Red Deer. The summary sheet has 2001 to 2051 with births,
  deaths and migration.
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
    # open.alberta.ca's CKAN API answered HTTP 500 on 2026-11-09, 2026-11-10 and
    # again on 2026-11-19: an outage to report as a skip; anything else is raised.
    except Exception as exc:  # noqa: BLE001 - only an outage is skipped
        skip_outage("open.alberta.ca", exc)
    return verdict("AB OPENDATA TBF", not failures)


async def _checks() -> int:
    failures = 0

    def check(ok: bool, label: str) -> None:
        nonlocal failures
        print(("OK: " if ok else "FAIL: ") + label)
        failures += 0 if ok else 1

    async with new_client():
        aax = await client.get_activity_index()
        check(
            aax.first_period == "1981-01" and aax.total_observations >= 548,
            f"get_activity_index -> {aax.total_observations} months, {aax.first_period} to "
            f"{aax.last_period}, latest {aax.observations[-1].value:.1f}",
        )
        check(len(aax.observations) == 24, "default is the latest 24 months")
        check(abs(aax.observations[-1].value) > 100, "index level above the 1981 base")
        check("January 1981 = 100" in aax.series, f"series title {aax.series!r}")
        check(aax.ogl_alberta and aax.attribution is not None, "AAX under OGL-Alberta")
        early = await client.get_activity_index(start="1981-01", end="1981-12")
        check(
            len(early.observations) == 12 and abs(early.observations[0].value - 100) < 0.01,
            "get_activity_index(1981) starts at 100",
        )

        alberta = await client.get_population_projection(start_year=2051, end_year=2051)
        check(
            alberta.edition >= 2026 and len(alberta.rows) == 1 and alberta.rows[0].projected,
            f"get_population_projection(alberta, 2051) -> edition {alberta.edition}, "
            f"{alberta.rows[:1]}",
        )
        check(
            (alberta.rows[0].total or 0) > 5_000_000,
            "Alberta 2051 medium above five million",
        )
        high = await client.get_population_projection(
            scenario="high", gender="any", start_year=2030, end_year=2030, ages=True
        )
        genders = {r.gender for r in high.rows}
        check(genders == {"women+", "men+", "all"}, f"three genders -> {sorted(genders)}")
        ages = high.rows[0].ages or {}
        check(
            len(ages) >= 100 and "0" in ages,
            f"single years of age -> {len(ages)}, last {list(ages)[-1:]}",
        )
        low = await client.get_population_projection(scenario="low", start_year=2051)
        check(
            (low.rows[0].total or 0) < (alberta.rows[0].total or 0),
            "low scenario below medium in 2051",
        )

        divisions = await client.get_population_projection(geography="census_division")
        check(
            not divisions.rows and "4806" in divisions.areas,
            f"census divisions list areas -> {len(divisions.areas)}",
        )
        calgary_cd = await client.get_population_projection(
            geography="census_division", area="4806", start_year=2026, end_year=2027
        )
        check(
            calgary_cd.area == "4806" and len(calgary_cd.rows) == 2,
            f"census division 4806 -> {calgary_cd.rows}",
        )
        cma = await client.get_population_projection(
            geography="census_metropolitan_area", area="edmonton", end_year=2001
        )
        check(
            cma.area == "Edmonton" and len(cma.rows) == 1 and not cma.rows[0].projected,
            f"CMA Edmonton 2001 estimate -> {cma.rows}",
        )
        try:
            await client.get_population_projection(geography="economic_region", scenario="low")
            check(False, "low scenario for an economic region should be refused")
        except InvalidInput:
            check(True, "sub-provincial low scenario refused")
        regions = await client.get_population_projection(geography="economic_region")
        check(bool(regions.areas), f"economic regions -> {regions.areas[:8]}")

        summary = await client.get_population_projection_summary()
        first, last = summary.rows[0], summary.rows[-1]
        check(
            first.year == 2001 and last.year == 2051 and last.projected and not first.projected,
            f"get_population_projection_summary -> {len(summary.rows)} years",
        )
        check(
            last.population == alberta.rows[0].total,
            "summary 2051 population equals the medium scenario total",
        )
        check(
            all(
                v is not None
                for v in (
                    last.births,
                    last.deaths,
                    last.net_interprovincial,
                    last.total_net_migration,
                    last.child_dependency_ratio,
                    last.elderly_dependency_ratio,
                    last.period,
                )
            ),
            f"summary 2051 components -> {last}",
        )
        check(summary.provenance.limits is None, "every summary column found")

        older = await client.get_population_projection_summary(edition=2025, end_year=2025)
        check(
            older.edition == 2025 and older.rows[-1].year == 2025 and older.rows[-1].projected,
            f"2025 edition summary -> {older.dataset}",
        )

    return failures


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
