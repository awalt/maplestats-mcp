"""Live smoke test for the City of Calgary module (data.calgary.ca).

Calls every client function against the real portal. First run 2026-11-19: 641 permits
issued in Bridgeland/Riverside (BRD) since 2020-01-01; 41,600 permits issued since
2025-01-01 adding 44,767 housing units; civic census 1968-2019, with 1,278,432
residents summed over the communities in 2019.
"""

from __future__ import annotations

import asyncio
import sys

from _smoke_common import skip_outage, verdict

from maplestats_mcp.modules.calgary import client
from maplestats_mcp.shared.errors import InvalidInput, NotFound, UpstreamUnavailable


async def main() -> int:
    failures = 0
    try:
        listing = await client.list_building_permits(
            community="BRD", start_date="2020-01-01", limit=3
        )
        first = listing.permits[0] if listing.permits else None
        print(f"OK: list_building_permits(BRD) total={listing.total_matches} first={first}")
        failures += not listing.permits or first is None or first.community_code != "BRD"
        failures += listing.provenance.licence is None or listing.provenance.as_of is None

        street = await client.list_building_permits(
            address_contains="17 AV SW", work_class_group="new", date_field="applied", limit=2
        )
        print(f"OK: list on 17 AV SW, new work, total={street.total_matches}")
        failures += street.total_matches == 0

        for group_by in (
            "community",
            "permit_class_group",
            "permit_class",
            "work_class_group",
            "permit_type",
            "status",
            "year",
            "month",
        ):
            summary = await client.summarize_building_permits(
                group_by,  # type: ignore[arg-type]
                start_date="2025-01-01",
                top=5,
            )
            top_group = summary.groups[0] if summary.groups else None
            print(
                f"OK: summarize({group_by}) total={summary.total_permits} "
                f"units={summary.total_housing_units} first={top_group}"
            )
            failures += not summary.groups or summary.total_permits == 0

        months = await client.summarize_building_permits(
            "month", start_date="2025-03-01", end_date="2025-03-31"
        )
        print(f"OK: March 2025 by month -> {[(g.key, g.permit_count) for g in months.groups]}")
        failures += (
            len(months.groups) != 1
            or months.groups[0].key != "2025-03"
            or months.groups[0].permit_count != months.total_permits
        )

        community = await client.get_community_populations(
            community="BRIDGELAND/RIVERSIDE", start_year=2010
        )
        latest = community.rows[0] if community.rows else None
        print(f"OK: community populations rows={len(community.rows)} latest={latest}")
        failures += latest is None or latest.census_year != 2019 or not latest.population

        city = await client.get_community_populations(by="total", limit=60, lang="fr")
        years = [row.census_year for row in city.rows]
        print(f"OK: summed {min(years)}-{max(years)} ({len(years)} years), {city.rows[0]}")
        failures += min(years) != 1968 or max(years) != 2019
        failures += city.provenance.licence is None

        try:
            await client.get_community_populations(community="NO SUCH PLACE")
            print("FAIL: unknown community did not raise")
            failures += 1
        except NotFound:
            print("OK: unknown community raises NotFound")
    except UpstreamUnavailable as exc:
        skip_outage("City of Calgary open data", exc)

    try:
        await client.list_building_permits(start_date="2026-13-01")
        print("FAIL: bad date did not raise")
        failures += 1
    except InvalidInput:
        print("OK: bad date raises InvalidInput")

    return verdict("Calgary", not failures)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
