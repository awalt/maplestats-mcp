"""Live smoke test for the CRA individual tax statistics client (cra_tax_stats).

Calls every client function against open.canada.ca and www.canada.ca, for every
covered edition: T1 tax years 2018-2024 and FSA tax years 2017-2021. Run from the
repository root with:

    uv run python scripts/smoke_test_cra_tax_stats.py
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable
from itertools import pairwise
from typing import Any

from _smoke_common import report_skipped_hosts, skip_outage, verdict

from maplestats_mcp.modules.cra_tax_stats import client, constants
from maplestats_mcp.shared.errors import InvalidInput, NotFound

_failures: list[str] = []


def _fail(message: str) -> None:
    _failures.append(message)
    print(f"FAIL: {message}")


async def _check(label: str, awaitable: Awaitable[Any]) -> Any:
    result = await awaitable
    print(f"OK: {label} -> {type(result).__name__}")
    return result


async def _expect(label: str, exc_type: type[Exception], awaitable: Awaitable[Any]) -> None:
    try:
        await awaitable
    except exc_type as exc:
        print(f"OK: {label} raises {exc_type.__name__} ({str(exc)[:90]})")
        return
    except Exception as exc:  # noqa: BLE001
        _fail(f"{label} raised {type(exc).__name__}: {exc}")
        return
    _fail(f"{label} did not raise {exc_type.__name__}")


def _value(rows: list[Any], **wanted: Any) -> float | None:
    for row in rows:
        if all(getattr(row, k) == v for k, v in wanted.items()):
            return row.value
    return None


async def _t1_editions() -> None:
    catalogue = await _check("list_tables(t1_final)", client.list_tables("t1_final"))
    if [e.tax_year for e in catalogue.editions] != sorted(constants.T1_EDITIONS):
        _fail(f"T1 editions listed: {[e.tax_year for e in catalogue.editions]}")
    for year in sorted(constants.T1_EDITIONS):
        listed = await _check(
            f"list_tables(t1_final, {year})", client.list_tables("t1_final", year)
        )
        have = {(t.table, t.area) for t in listed.tables}
        needed = {("1", "ca"), ("2", "ca"), ("3", "ca"), ("4", "ca")}
        if year <= 2023:
            needed.add(("5", "ca"))
        if not needed <= have:
            _fail(f"{year}: missing national tables {sorted(needed - have)}")
        if year != 2021 and ("2", "ab") not in have:
            _fail(f"{year}: no Table 2 file for Alberta")

        # Table 1's Canada total income (all returns) must equal Table 2's
        # "Total income assessed" total: Table 1 is in millions to 2021, so it is
        # read to the nearest million there.
        t1 = await _check(
            f"get_t1_table({year}, 1)",
            client.get_t1_table(year, 1, group="Canada", item="Total income assessed"),
        )
        t2 = await _check(
            f"get_t1_table({year}, 2)",
            client.get_t1_table(year, 2, item="Total income assessed", group="Total"),
        )
        one = _value(t1.rows, return_type="All returns", measure="amount")
        two = _value(t2.rows, item="Total income assessed", measure="amount")
        if one is None or two is None:
            _fail(f"{year}: total income missing (table 1 {one}, table 2 {two})")
        elif abs(one - two) > 1000:
            _fail(f"{year}: Table 1 total income {one:,.0f} vs Table 2 {two:,.0f} (thousands)")
        else:
            print(f"   {year}: total income assessed {one:,.0f} thousand dollars (Tables 1 and 2)")
        if not 1.0e9 < (one or 0) < 3.0e9:
            _fail(f"{year}: total income {one} is not in thousands of dollars")


async def _t1_other_tables() -> None:
    t3_old = await _check("get_t1_table(2018, 3)", client.get_t1_table(2018, 3, limit=5000))
    if "Proprietorships/Partnerships" not in {r.group for r in t3_old.rows}:
        _fail("2018 Table 3: the Proprietorships/Partnerships group was split")
    t3_new = await _check("get_t1_table(2024, 3)", client.get_t1_table(2024, 3, group="Canada"))
    if not any(r.item == "Employment Income" for r in t3_new.rows):
        _fail("2024 Table 3: no Employment Income row for Canada")
    t4 = await _check(
        "get_t1_table(2024, 4, area=on)",
        client.get_t1_table(2024, 4, area="on", item="Total income assessed"),
    )
    if not any(r.group.startswith("Age group") for r in t4.rows):
        _fail("2024 Table 4 Ontario: no age-group columns")
    t5 = await _check(
        "get_t1_table(2023, 5)", client.get_t1_table(2023, 5, item="Total tax payable")
    )
    if _value(t5.rows, group="Alberta", measure="amount") is None:
        _fail("2023 Table 5: no Alberta total tax payable")
    fr = await _check(
        "get_t1_table(2022, 2, area=nr, fr)",
        client.get_t1_table(2022, 2, area="nr", item="Employment income", lang="fr"),
    )
    if not any(r.item_fr for r in fr.rows):
        _fail("2022 Table 2: no French line item (Poste)")
    if "Licence" not in (fr.provenance.licence or ""):
        _fail(f"French provenance licence: {fr.provenance.licence!r}")


async def _t1_series() -> None:
    series = await _check(
        "get_t1_series(1, Total income assessed)",
        client.get_t1_series(1, "Total income assessed", measure="amount"),
    )
    if series.missing_years:
        _fail(f"Table 1 series missing {series.missing_years}")
    values = [r.value for r in series.rows]
    if len(values) != len(constants.T1_EDITIONS) or any(
        not 0.8 < b / a < 1.25 for a, b in pairwise(values)
    ):
        _fail(f"Table 1 series not in one unit: {values}")
    print(f"   total income 2018-2024 (thousands): {[f'{v:,.0f}' for v in values]}")
    employment = await _check(
        "get_t1_series(2, Employment income, group=100000 - 149999)",
        client.get_t1_series(2, "Employment income", group="100000 - 149999", area="ab"),
    )
    print(
        f"   Alberta employment income rows: {len(employment.rows)}, missing {employment.missing_years}"
    )
    if 2021 not in employment.missing_years:
        _fail("Alberta Table 2 for 2021 is a PDF upstream and should be missing")


async def _fsa() -> None:
    catalogue = await _check("list_tables(fsa)", client.list_tables("fsa"))
    if [e.tax_year for e in catalogue.editions] != sorted(constants.FSA_EDITIONS):
        _fail(f"FSA editions listed: {[e.tax_year for e in catalogue.editions]}")
    for year in sorted(constants.FSA_EDITIONS):
        listed = await _check(f"list_tables(fsa, {year})", client.list_tables("fsa", year))
        if {"1a", "1b", "1e", "2"} - {t.table for t in listed.tables}:
            _fail(f"FSA {year}: tables found {[t.table for t in listed.tables]}")
        table = await _check(
            f"get_fsa_table({year}, 1a, T5K)", client.get_fsa_table(year, "1a", fsa=["T5K"])
        )
        income = next((r.value for r in table.rows if r.item.lower() == "total income"), None)
        print(f"   FSA T5K {year}: total income {income} thousand dollars")
        if income is None or not 1.0e5 < income < 1.0e7:
            _fail(f"FSA {year} T5K total income {income} is not in thousands of dollars")
    alberta = await _check(
        "get_fsa_table(2021, 1b, province=ab, Total)",
        client.get_fsa_table(2021, "1b", fsa=["Total"], province="48"),
    )
    if not alberta.rows or any(r.province != "ab" for r in alberta.rows):
        _fail("FSA 2021 Alberta total row missing")
    ages = await _check(
        "get_fsa_table(2019, 2, province=on)",
        client.get_fsa_table(2019, "2", province="on", limit=50),
    )
    if not ages.truncated:
        _fail("FSA 2019 Table 2 Ontario should hold more than 50 rows")
    sources = await _check(
        "get_fsa_table(2018, 1e, H2X)", client.get_fsa_table(2018, "1e", fsa=["H2X"])
    )
    if {r.measure for r in sources.rows} != {"number", "amount"}:
        _fail("FSA 2018 Table 1e: number and amount columns not both found")
    series = await _check(
        "get_fsa_series(T5K, Total income)", client.get_fsa_series("T5K", item="Total income")
    )
    values = [r.value for r in series.rows]
    print(f"   T5K total income 2017-2021 (thousands): {values}")
    if series.missing_years or any(not 0.7 < b / a < 1.4 for a, b in pairwise(values)):
        _fail(f"FSA series not in one unit or incomplete: {values}, missing {series.missing_years}")


async def _errors() -> None:
    await _expect("t1 tax_year 2016", InvalidInput, client.get_t1_table(2016, 1))
    await _expect("t1 Table 1 for Alberta", NotFound, client.get_t1_table(2024, 1, area="ab"))
    await _expect("t1 2021 Table 2 Alberta (PDF)", NotFound, client.get_t1_table(2021, 2, "ab"))
    await _expect("t1 2024 Table 5 (not published)", NotFound, client.get_t1_table(2024, 5))
    await _expect("fsa 2021 Table 1c (no English national file)", NotFound,
                  client.get_fsa_table(2021, "1c", fsa=["T5K"]))  # fmt: skip
    await _expect("fsa bad code", InvalidInput, client.get_fsa_table(2020, "1a", fsa=["12345"]))
    await _expect("series unknown item", NotFound, client.get_t1_series(1, "No such item"))
    try:
        await client.get_t1_table(2030, 1, lang="fr")
    except InvalidInput as exc:
        if "année" not in str(exc):
            _fail(f"French error is not French: {exc}")
        else:
            print("OK: French InvalidInput")


async def main() -> int:
    ok = True
    for name, step in (
        ("T1 editions", _t1_editions),
        ("T1 other tables", _t1_other_tables),
        ("T1 series", _t1_series),
        ("FSA", _fsa),
        ("errors", _errors),
    ):
        try:
            await step()
        except Exception as exc:  # noqa: BLE001
            try:
                skip_outage(f"cra_tax_stats ({name})", exc, rest_runs=True)
            except Exception as other:  # noqa: BLE001
                _fail(f"{name}: {type(other).__name__}: {other}")
    ok = not _failures
    report_skipped_hosts("smoke_test_cra_tax_stats.py")
    return verdict("CRA TAX STATS", ok)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
