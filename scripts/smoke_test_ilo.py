"""Live smoke test for the ilo module: calls the real ILOSTAT SDMX API (not
mocks) for every client function and every tool, per AGENTS.md's "lesson
from auditing the StatCan module".

Usage:
    uv run python scripts/smoke_test_ilo.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from _smoke_common import skip_outage, verdict
from fastmcp import Client
from mcp.types import TextContent

from maplestats_mcp.modules.ilo import client, constants
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

    # 1,215 dataflows on 2026-11-08.
    for query, expected, lang in (
        ("unemployment rate by sex and age", "DF_UNE_DEAP_SEX_AGE_RT", "en"),
        ("labour force participation rate", "DF_EAP_DWAP_SEX_AGE_RT", "en"),
        ("minimum wage", "DF_EAR_INEE_CUR_NB", "en"),
        ("labour income share", "DF_LAP_2GDP_NOC_RT", "en"),
        ("taux de chômage par sexe et âge", "DF_UNE_DEAP_SEX_AGE_RT", "fr"),
    ):
        found = await client.search_datasets(query, limit=5, lang=lang)
        ids = [d.id for d in found.datasets]
        print(f"OK: search {query!r} -> {found.total_matches} matches, top {ids[:3]}")
        if expected not in ids:
            print(f"FAIL: {expected} not in the top 5 for {query!r}")
            ok = False

    for dataset, lang in (("DF_UNE_DEAP_SEX_AGE_RT", "fr"), ("DF_EAR_EMTA_SEX_CUR_NB", "en")):
        structure = await client.describe_dataset(dataset, lang=lang)
        print(
            f"OK: describe {dataset} -> {structure.key_template} e.g. {structure.example_key!r}, "
            f"updated {structure.last_updated}, {[d.total_codes for d in structure.dimensions]}"
        )
        ok &= all(d.codes for d in structure.dimensions) and "CAN" in structure.example_key

    une = await client.get_data(
        "DF_UNE_DEAP_SEX_AGE_RT", "CAN+USA.A.UNE_DEAP_RT.SEX_T.AGE_YTHADULT_YGE15", last_n=2
    )
    print(
        "OK: unemployment ->",
        [(s.key, s.source, s.latest_period, s.latest_value) for s in une.series],
    )
    ok &= (
        len(une.series) == 2 and une.rows[0].ref_area == "CAN" and une.rows[0].unit == "Percentage"
    )
    # ILOSTAT's own data API (rplumber.ilo.org) gave 6.819 for Canada, 2025.
    canada_2025 = next(
        (r.value for r in une.rows if r.ref_area == "CAN" and r.period == "2025"), None
    )
    print(f"OK: Canada 2025 unemployment = {canada_2025}")
    ok &= canada_2025 is not None and abs(canada_2025 - 6.819) < 0.05

    monthly = await client.get_data(
        "DF_UNE_DEAP_SEX_AGE_RT",
        "CAN.M.UNE_DEAP_RT.SEX_T.AGE_YTHADULT_YGE15",
        start_period="2026-01",
        lang="fr",
    )
    print(
        "OK: monthly (fr) ->",
        [(r.period, r.value) for r in monthly.rows[-3:]],
        monthly.series[0].frequency,
    )
    ok &= monthly.rows[0].period.startswith("2026-M")

    for indicator, spec in constants.INDICATORS.items():
        result = await client.compare_countries(indicator, compare_with=["G7"])
        canada = result.countries[0]
        print(
            f"OK: {indicator} -> CA {canada.latest_period} {canada.latest_value} "
            f"({canada.unit}), rank {result.canada_rank}/{result.ranked_countries} in "
            f"{result.rank_period}"
        )
        ok &= canada.area_code == "CAN" and len(result.countries) >= 4
        if "Q" in spec.frequencies and indicator == "unemployment_rate":
            quarterly = await client.compare_countries(
                indicator, ["US", "UK", "AUS"], sex="female", frequency="quarterly", last_n=4
            )
            print(
                f"OK: {indicator} quarterly female -> {[c.area_code for c in quarterly.countries]}"
            )
            ok &= quarterly.sex == "female"

    french = await client.compare_countries("youth_unemployment_rate", ["WORLD", "EU27"], lang="fr")
    print(
        f"OK: compare (fr) -> {french.indicator_label} | "
        f"{[(c.area_code, c.area_name) for c in french.countries]}"
    )
    ok &= french.indicator_label.startswith("Taux de chômage des jeunes")
    return ok


async def errors() -> bool:
    ok = True
    ok &= await _expect_error(
        "short key", client.get_data("DF_UNE_DEAP_SEX_AGE_RT", "CAN.A"), InvalidInput
    )
    ok &= await _expect_error(
        "unknown area",
        client.get_data("DF_UNE_DEAP_SEX_AGE_RT", "ZZZ.A.UNE_DEAP_RT.SEX_T.AGE_YTHADULT_YGE15"),
        InvalidInput,
    )
    ok &= await _expect_error("unknown dataset", client.describe_dataset("DF_NOPE"), NotFound)
    ok &= await _expect_error(
        "future period",
        client.get_data(
            "DF_UNE_DEAP_SEX_AGE_RT",
            "CAN.A.UNE_DEAP_RT.SEX_T.AGE_YTHADULT_YGE15",
            start_period="2040",
        ),
        NotFound,
    )
    ok &= await _expect_error(
        "monthly modelled",
        client.compare_countries("labour_income_share", frequency="monthly"),
        InvalidInput,
    )
    return ok


async def through_server() -> bool:
    """Every tool once through call_tool, as a client reaches it (cached calls)."""
    ok = True
    calls = [
        ("ilo_search_datasets", {"query": "chômage", "lang": "fr"}),
        ("ilo_describe_dataset", {"dataset": "DF_UNE_DEAP_SEX_AGE_RT"}),
        (
            "ilo_get_data",
            {
                "dataset": "DF_UNE_DEAP_SEX_AGE_RT",
                "key": "CAN+USA.A.UNE_DEAP_RT.SEX_T.AGE_YTHADULT_YGE15",
                "last_n": 2,
            },
        ),
        ("ilo_compare_countries", {"indicator": "unemployment_rate", "compare_with": ["G7"]}),
    ]
    async with Client(mcp) as session:
        for name, args in calls:
            result = await session.call_tool("call_tool", {"name": name, "arguments": args})
            text = next(c.text for c in result.content if isinstance(c, TextContent))
            data = json.loads(text)
            print(f"OK: call_tool({name}) -> {sorted(data)[:6]}")
            ok &= not result.is_error
    return ok


async def run() -> bool:
    ok = await main()
    ok &= await errors()
    ok &= await through_server()
    return ok


async def rplumber_route() -> bool:
    """The comparisons and the datasets behind them read through ILOSTAT's rplumber API
    when sdmx.ilo.org refuses requests (it answered the IIS 403 page on 2026-11-17), and
    through it alone here: one preset of each key layout, with the values the ILO's own
    data API gave on 2026-11-08 (Canada's 2025 unemployment rate 6.819, US weekly hours
    37.54). The route is chosen by the client, so this passes on either API; the note
    in the result says which one served it."""
    ok = True
    layouts = (
        ("unemployment_rate", "sex and age"),
        ("weekly_hours_worked", "sex only"),
        ("average_monthly_earnings_ppp", "sex and currency"),
        ("minimum_wage_ppp", "currency only"),
        ("labour_income_share", "no breakdown"),
    )
    for indicator, layout in layouts:
        result = await client.compare_countries(indicator, compare_with=["USA"], last_n=3)
        canada, usa = result.countries[0], result.countries[1]
        via = "rplumber" if any("rplumber" in n for n in result.notes) else "SDMX"
        print(
            f"OK: {indicator} ({layout}) via {via} -> CA {canada.latest_period} "
            f"{canada.latest_value}, US {usa.latest_period} {usa.latest_value}, rank "
            f"{result.canada_rank}/{result.ranked_countries}"
        )
        ok &= canada.area_code == "CAN" and usa.area_code == "USA" and len(canada.observations) <= 3
    hours = await client.compare_countries("weekly_hours_worked", compare_with=["USA"], last_n=3)
    us_2025 = next((o.value for o in hours.countries[1].observations if o.period == "2025"), None)
    ok &= us_2025 is not None and abs(us_2025 - 37.54) < 0.05
    monthly = await client.compare_countries("unemployment_rate", frequency="monthly", last_n=3)
    print(
        f"OK: monthly unemployment -> {[(o.period, o.value) for o in monthly.countries[0].observations]}"
    )
    ok &= all(
        o.period.startswith("20") and "-M" in o.period for o in monthly.countries[0].observations
    )
    data = await client.get_data(
        "DF_UNE_DEAP_SEX_AGE_RT", "CAN+USA.A.UNE_DEAP_RT.SEX_T.AGE_YTHADULT_YGE15", last_n=2
    )
    canada_2025 = next(
        (r.value for r in data.rows if r.ref_area == "CAN" and r.period == "2025"), None
    )
    print(f"OK: get_data unemployment -> Canada 2025 = {canada_2025}, {len(data.rows)} rows")
    ok &= canada_2025 is not None and abs(canada_2025 - 6.819) < 0.05
    return ok


async def guarded() -> int:
    # ILOSTAT's SDMX API answers an IIS 403 "Access is denied" page now and then (2026-11-08
    # for a moment, 2026-11-17 for every request): an outage skips the SDMX checks, which
    # need that API, but the rplumber route is still checked; any other error still fails.
    ok = True
    try:
        ok = await run()
        print("ALL OK" if ok else "SOME CHECKS FAILED")
    except Exception as exc:  # noqa: BLE001
        skip_outage("sdmx.ilo.org", exc, rest_runs=True)
    try:
        ok &= await rplumber_route()
    except Exception as exc:  # noqa: BLE001
        skip_outage("rplumber.ilo.org", exc)
    return verdict("ILO", ok)


if __name__ == "__main__":
    sys.exit(asyncio.run(guarded()))
