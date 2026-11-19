"""Live smoke test for the City of Toronto module (open.toronto.ca DataStore tables).

Every client function is called against the live portal; the checks are
ones the published tables should keep satisfying (140 neighbourhoods, 25
wards, scores between 0 and 100), not today's exact counts.
"""

from __future__ import annotations

import asyncio
import sys

from maplestats_mcp.modules.toronto import client


async def main() -> int:
    failures = 0

    profile = await client.get_neighbourhood_profile("Annex", characteristic="Renter")
    renter = next((r for r in profile.rows if r.characteristic == "Renter"), None)
    print(f"OK: Annex ({profile.neighbourhood_number}) renters 2016: {renter}")
    failures += renter is None or renter.value_number is None or not profile.topics
    for year in (2011, 2006, 2001):
        older = await client.get_neighbourhood_profile("72", census_year=year, limit=1)
        print(f"OK: Regent Park {year}: {older.rows[0].characteristic} = {older.rows[0].value}")
        failures += older.neighbourhood != "Regent Park" or older.total_matched < 500

    every = await client.get_apartment_evaluations(latest_only=False, limit=1)
    latest = await client.get_apartment_evaluations(limit=3)
    print(
        f"OK: RentSafeTO {every.total_matched} evaluations, {latest.total_matched} buildings; "
        f"lowest {[(e.address, e.score) for e in latest.evaluations]}"
    )
    failures += not 0 < latest.total_matched < every.total_matched
    ward = await client.get_apartment_evaluations(ward="Scarborough Southwest", limit=1)
    failures += ward.total_matched == 0
    summary = await client.summarize_apartment_scores()
    print(f"OK: wards {len(summary.groups)}, city {summary.city}")
    failures += len(summary.groups) != 25 or summary.buildings != latest.total_matched
    failures += not 0 <= (summary.city.min_score or -1) <= (summary.city.max_score or 101) <= 100
    by_type = await client.summarize_apartment_scores(group_by="property_type")
    print(f"OK: property types {[(g.key, g.buildings) for g in by_type.groups]}")

    rentals = await client.summarize_short_term_rentals()
    print(f"OK: short-term rentals {rentals.registrations} in {len(rentals.groups)} wards")
    failures += rentals.registrations == 0 or len(rentals.groups) < 25
    fsa = await client.summarize_short_term_rentals(group_by="postal_code")
    print(f"OK: busiest FSAs {[(g.key, g.registrations) for g in fsa.groups[:3]]}")

    pizza = await client.search_dinesafe(establishment="pizza", address="queen", limit=2)
    closed = await client.search_dinesafe(status="Closed", limit=2)
    print(f"OK: DineSafe pizza on Queen {pizza.total_matched}, closures {closed.total_matched}")
    print(f"    latest closure {closed.inspections[0] if closed.inspections else None}")
    failures += pizza.total_matched == 0 or closed.total_matched == 0
    failures += any("None" in (i.address or "").split() for i in pizza.inspections)

    council = await client.get_councillors()
    wards = {m.ward for m in council.members if m.ward}
    print(f"OK: council {len(council.members)} members, {len(wards)} wards")
    failures += len(wards) != 25 or not any(m.role == "Mayor" for m in council.members)
    one = await client.get_councillors(ward="Spadina-Fort York")
    print(f"OK: ward 10 councillor {[m.name for m in one.members]}")
    failures += [m.ward for m in one.members] != ["10"]

    for model in (140, 158):
        overlap = await client.get_ward_neighbourhoods("10", neighbourhood_model=model)
        total = sum(n.share_of_ward for n in overlap.neighbourhoods)
        print(
            f"OK: ward 10 ({overlap.ward_area_km2} km2), {model} model: "
            f"{[(n.neighbourhood, n.share_of_ward) for n in overlap.neighbourhoods]}"
        )
        failures += not overlap.neighbourhoods or not 0.95 <= total <= 1.01

    renters = await client.compare_neighbourhoods("Renter", divide_by_parent=True, limit=3)
    print(
        f"OK: highest renter shares 2016 {[(v.neighbourhood, v.share) for v in renters.neighbourhoods]}"
        f", city {renters.city.share}"
    )
    failures += renters.total_matched != 140 or not 0.3 < (renters.city.share or 0) < 0.7
    rented = await client.compare_neighbourhoods("Rented", census_year=2006, divide_by_parent=True)
    failures += rented.city.share is None

    profile = await client.get_ward_profile("10")
    print(
        f"OK: ward profile {profile.ward_name}: {profile.councillor and profile.councillor.name}, "
        f"{profile.scores.ward.buildings} buildings, mean {profile.scores.ward.mean_score}, "
        f"{len(profile.neighbourhoods)} neighbourhoods"
    )
    placed = sum(n.buildings_evaluated for n in profile.neighbourhoods)
    failures += profile.councillor is None or len(profile.sources) != 5
    failures += placed + profile.buildings_without_coordinates != profile.scores.ward.buildings
    failures += any(n.renter_share is None for n in profile.neighbourhoods)

    print("TORONTO SMOKE TEST " + ("PASSED" if not failures else f"FAILED ({failures})"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
