"""Live smoke test for the bcer module: reads BCER's real bulk files from
iris.bcogc.ca (not mocks) and calls every client function and every tool, per
AGENTS.md's "lesson from auditing the StatCan module".

It is polite: one request at a time through the module's own limiter, small ranges,
and the 124 MB production zip is only ever read by range requests (one well's history is
about 1 MB; a month of province-wide production reads the 3.7 MB 2025-to-present file).
The values checked below were read from the files on 2026-11-17 (production figures of a
well that has stopped changing, a historic casing record, a directional survey); a BCER
revision of those old rows would show here as a failed check, not as a code fault.

Usage:
    uv run python scripts/smoke_test_bcer.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

from fastmcp import Client
from mcp.types import TextContent

from maplestats_mcp.modules.bcer import client
from maplestats_mcp.server import mcp
from maplestats_mcp.shared.errors import InvalidInput, NotFound


def _check(label: str, condition: bool, detail: object = "") -> bool:
    print(f"{'OK' if condition else 'FAIL'}: {label} {detail}")
    return condition


async def _expect_error(label: str, coro, exc_type: type[Exception]) -> bool:
    try:
        await coro
    except exc_type as exc:
        print(f"OK: {label} -> {type(exc).__name__}: {str(exc)[:110]}")
        return True
    except Exception as exc:  # noqa: BLE001 - smoke test wants to see everything
        print(f"FAIL: {label} -> {type(exc).__name__}: {exc}")
        return False
    print(f"FAIL: {label} -> no error")
    return False


async def files() -> bool:
    ok = True
    started = time.monotonic()
    listing = await client.list_files()
    by_name = {f.name: f for f in listing.files}
    ok &= _check(
        "list_files: 14 files, all available",
        len(listing.files) == 14 and all(f.available for f in listing.files),
        f"{time.monotonic() - started:.1f} s; {[f.name for f in listing.files if not f.available]}",
    )
    ok &= _check(
        "list_files: sizes and dates",
        5_000_000 < (by_name["well_index.csv"].size_bytes or 0) < 40_000_000
        and (by_name["prod_csv.zip"].size_bytes or 0) > 50_000_000
        and by_name["well_index.csv"].last_modified is not None,
        {n: (by_name[n].size_bytes, str(by_name[n].last_modified)) for n in list(by_name)[:3]},
    )
    ok &= _check(
        "list_files: terms stated, no licence claimed",
        "states no licence" in listing.terms
        and listing.provenance.commercial_use == "unknown"
        and "Open Government Licence" not in (listing.provenance.licence or "")
        and "check with BCER" in listing.provenance.caveats[0],
        listing.provenance.caveats[0][:80],
    )
    detailed = await client.list_files(include_members=True, lang="fr")
    drill = {f.name: f for f in detailed.files}["drill_csv.zip"]
    prod = {f.name: f for f in detailed.files}["prod_csv.zip"]
    ok &= _check(
        "list_files(include_members): members, readme counts and history date",
        len(drill.members or []) == 42
        and (drill.record_counts or {}).get("wells", 0) > 30_000
        and bool(drill.history_to)
        and "zone_prd_2025_to_present.csv" in {m.name for m in prod.members or []},
        f"{len(drill.members or [])} members; history to {drill.history_to}; "
        f"wells {(drill.record_counts or {}).get('wells')}",
    )
    return ok


async def wells() -> bool:
    ok = True
    started = time.monotonic()
    one = await client.search_wells(well_authorization="1811")
    row = one.rows[0] if one.rows else None
    ok &= _check(
        "search_wells WA 1811",
        row is not None
        and row.uwi == "200D057B094H0200"
        and row.well_name == "STRATHCONA ET AL WEASEL D- 057-B/094-H-02"
        and (row.first_production_period, row.last_production_period) == ("1966-01", "2020-03")
        and abs((row.surface_latitude or 0) - 57.047828) < 1e-4
        and abs((row.surface_longitude or 0) + 120.704642) < 1e-4
        and bool(row.operator_name),
        f"{time.monotonic() - started:.1f} s; {row.operator_name if row else None}, index "
        f"{one.index_rows:,} rows",
    )
    many = await client.search_wells(status="ABAN", limit=5)
    ok &= _check(
        "search_wells status ABAN pages and counts wells",
        many.rows_matched > 10_000 and many.wells_matched > 5_000 and many.returned == 5,
        f"{many.rows_matched:,} rows, {many.wells_matched:,} wells; {many.provenance.limits}",
    )
    operator = await client.search_wells(
        operator="Pacific Canbriam", status="DRIL,WAG,ACT", limit=3
    )
    ok &= _check(
        "search_wells by operator name",
        operator.rows_matched > 20
        and all("Canbriam" in (r.operator_name or "") for r in operator.rows),
        f"{operator.rows_matched} rows; {operator.notes[0][:80]}",
    )
    montney = await client.search_wells(formation_code="5000", name="altares", limit=3)
    ok &= _check(
        "search_wells formation 5000 (Montney) and name",
        montney.rows_matched > 20 and all("ALTARES" in (r.well_name or "") for r in montney.rows),
        f"{montney.rows_matched} rows",
    )
    return ok


async def production() -> bool:
    ok = True
    started = time.monotonic()
    recent = await client.get_production(
        well_authorization="101", from_period="2025-01", to_period="2025-03"
    )
    months = {m.period: m for m in recent.monthly_totals}
    ok &= _check(
        "production WA 101, 2025-01..03 (one small member, stopped at the well)",
        recent.complete
        and [m.member for m in recent.members_read] == ["zone_prd_2025_to_present.csv"]
        and (months["2025-01"].gas_e3m3, months["2025-01"].oil_m3, months["2025-01"].water_m3)
        == (5.9, 36.4, 1036.5)
        and months["2025-03"].gas_e3m3 == 5.3
        and recent.records[0].uwi == "100060608613W600",
        f"{time.monotonic() - started:.1f} s; read {recent.members_read[0].read_bytes:,} of "
        f"{recent.members_read[0].member_bytes:,} B",
    )
    started = time.monotonic()
    history = await client.get_production(well_authorization="101")
    read = sum(m.read_bytes for m in history.members_read)
    ok &= _check(
        "production WA 101, whole history across four period files",
        history.complete
        and history.records_matched == 820
        and len(history.members_read) == 4
        and read < 3_000_000
        and history.monthly_totals[0].period == "1955-02",
        f"{time.monotonic() - started:.1f} s; {read:,} B read of 61.6 MB; "
        f"{history.records_matched} rows, first {history.monthly_totals[0].period}, "
        f"last {history.monthly_totals[-1].period}",
    )
    started = time.monotonic()
    late = await client.get_production(well_authorization="55956")
    ok &= _check(
        "production WA 55956, no period: files before its first production are skipped",
        late.complete
        and [m.member for m in late.members_read] == ["zone_prd_2025_to_present.csv"]
        and any("Not read" in n for n in late.notes)
        and late.records_matched >= 2,
        f"{time.monotonic() - started:.1f} s; {late.records_matched} rows; "
        f"{late.members_read[0].read_bytes:,} B read",
    )
    started = time.monotonic()
    canbriam = await client.get_production(
        operator="Pacific Canbriam", from_period="2026-01", to_period="2026-03", limit=3
    )
    ok &= _check(
        "production by operator (Canbriam, 2026-01..03)",
        canbriam.complete
        and (canbriam.wells_selected or 0) > 300
        and len(canbriam.monthly_totals) == 3
        and all(m.gas_e3m3 > 100_000 for m in canbriam.monthly_totals)
        and canbriam.records_returned == 3,
        f"{time.monotonic() - started:.1f} s; {canbriam.wells_selected} wells; "
        f"{[(m.period, m.wells, m.gas_e3m3) for m in canbriam.monthly_totals]}",
    )
    started = time.monotonic()
    province = await client.get_production(from_period="2026-01", to_period="2026-01", limit=0)
    month = province.monthly_totals[0]
    ok &= _check(
        "production province-wide, 2026-01",
        province.complete
        and month.wells is not None
        and month.wells > 5_000
        and month.gas_e3m3 > 3_000_000
        and province.records == [],
        f"{time.monotonic() - started:.1f} s; {month.wells:,} wells, gas {month.gas_e3m3:,.0f} "
        f"e3m3, oil {month.oil_m3:,.0f} m3; {province.records_matched:,} rows",
    )
    by_uwi = await client.get_production(uwi="100060608613W600", from_period="2026-09")
    ok &= _check(
        "production by UWI",
        by_uwi.wells_selected == 1 and by_uwi.records_matched == 1,
        by_uwi.selection,
    )
    return ok


async def records() -> bool:
    ok = True
    started = time.monotonic()
    casings = await client.get_drilling_records(well_authorization="1811", table="casings")
    ok &= _check(
        "drilling casings WA 1811",
        [r["Casing Shoe Depth (m)"] for r in casings.rows] == ["156.4", "1203.9"]
        and casings.complete,
        f"{time.monotonic() - started:.1f} s; {casings.provenance.limits}",
    )
    events = await client.get_drilling_records(well_authorization="101", table="compl_wo", limit=3)
    ok &= _check(
        "drilling compl_wo WA 101 (10.7 MB member, stopped at the well)",
        events.returned == 3
        and events.members_read[0].read_bytes < 2_000_000
        and events.columns[4] == "Wa_num",
        f"{events.rows_matched} rows; read {events.members_read[0].read_bytes:,} B",
    )
    header = await client.get_drilling_records(well_authorization="59263", table="wells")
    ok &= _check(
        "drilling wells table WA 59263",
        header.rows_matched == 1 and header.rows[0]["Surf Nad83 Lat"] == "56162412",
        header.rows[0]["Well Name"] if header.rows else None,
    )
    frac = await client.get_fracture_records(well_authorization="2777")
    ok &= _check(
        "fracture WA 2777",
        frac.rows_matched == 1 and frac.rows[0]["TOTAL FLUID PUMPED (m3)"] == "117.2",
        frac.rows[0]["COMPLTN DATE"] if frac.rows else None,
    )
    perf = await client.get_fracture_records(well_authorization="2777", table="perf")
    ok &= _check(
        "perforations WA 2777",
        perf.rows_matched == 1 and perf.rows[0]["COMPLTN TOP DEPTH (m)"] == "1483.8",
        perf.provenance.limits,
    )
    interval = await client.get_fracture_records(
        well_authorization="3010", table="perf_net_interval", limit=5
    )
    ok &= _check(
        "perf_net_interval WA 3010",
        interval.rows_matched >= 2 and interval.rows[0]["INTERVAL TOP DEPTH (m)"] == "1463.5",
        interval.rows_matched,
    )
    started = time.monotonic()
    survey = await client.get_directional_survey(well_authorization="3488", limit=4)
    ok &= _check(
        "directional survey WA 3488",
        survey.rows_matched == 206
        and survey.returned == 4
        and [r["Measured Depth (m)"] for r in survey.rows[:2]] == ["0", "30"]
        and survey.rows[1]["Inclination (deg)"] == ".34",
        f"{time.monotonic() - started:.1f} s; read {survey.members_read[0].read_bytes:,} of "
        f"{survey.members_read[0].member_bytes:,} B",
    )
    return ok


async def reference() -> bool:
    ok = True
    plants = await client.search_facilities(facility_type="Gas Processing Plant", limit=3)
    ok &= _check(
        "facility index, gas processing plants",
        plants.rows_matched > 100 and plants.file_date is not None and plants.returned == 3,
        f"{plants.rows_matched} rows, print date {plants.file_date}",
    )
    capacity = await client.search_facilities(kind="capacity", limit=3)
    ok &= _check(
        "gas plant capacities",
        capacity.rows_matched > 100 and "Raw Gas (e3m3/d)" in capacity.columns,
        f"{capacity.rows_matched} plants, extract date {capacity.file_date}",
    )
    operators = await client.get_reference_table(table="operators", query="tourmaline")
    ok &= _check(
        "reference operators 'tourmaline'",
        any(r["Client Id"] == "00831" for r in operators.rows),
        [(r["Client Id"], r["Client Name"]) for r in operators.rows],
    )
    codes = await client.get_reference_table(table="codes", query="montney")
    ok &= _check(
        "reference codes 'montney'",
        any(r["Table ID"] == "FORT" and r["Code"] == "5000" for r in codes.rows),
        [(r["Code"], r["Description"]) for r in codes.rows],
    )
    areas = await client.get_reference_table(table="areas", query="altares")
    ok &= _check("reference areas 'altares'", areas.rows_matched == 1, areas.rows[:1])
    return ok


async def errors() -> bool:
    ok = True
    ok &= await _expect_error(
        "bad well number", client.search_wells(well_authorization="x"), InvalidInput
    )
    ok &= await _expect_error(
        "unknown operator", client.search_wells(operator="zzzz qqqq"), NotFound
    )
    ok &= await _expect_error("province without a period", client.get_production(), InvalidInput)
    ok &= await _expect_error(
        "unknown drilling table",
        client.get_drilling_records(well_authorization="1", table="nope"),
        InvalidInput,
    )
    ok &= await _expect_error(
        "two wells for a one-well tool",
        client.get_directional_survey(well_authorization="1, 2"),
        InvalidInput,
    )
    return ok


async def through_server() -> bool:
    """Every tool once through call_tool, as a client reaches it."""
    ok = True
    calls = [
        ("bcer_list_files", {}),
        ("bcer_search_wells", {"well_authorization": "1811", "lang": "fr"}),
        ("bcer_get_production", {"well_authorization": "101", "from_period": "2025-01"}),
        ("bcer_get_drilling_records", {"well_authorization": "1811", "table": "casings"}),
        ("bcer_get_fracture_records", {"well_authorization": "2777"}),
        ("bcer_get_directional_survey", {"well_authorization": "3488", "limit": 3}),
        ("bcer_search_facilities", {"query": "canbriam", "limit": 3}),
        ("bcer_get_reference_table", {"table": "codes", "query": "montney"}),
    ]
    async with Client(mcp) as session:
        for name, args in calls:
            result = await session.call_tool("call_tool", {"name": name, "arguments": args})
            text = next(c.text for c in result.content if isinstance(c, TextContent))
            data = json.loads(text)
            ok &= _check(f"call_tool({name})", not result.is_error, sorted(data)[:6])
    return ok


async def run() -> int:
    ok = await files()
    ok &= await wells()
    ok &= await production()
    ok &= await records()
    ok &= await reference()
    ok &= await errors()
    ok &= await through_server()
    print("ALL OK" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
