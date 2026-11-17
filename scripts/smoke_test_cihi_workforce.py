"""Live smoke test for modules/cihi/workforce's client.py: calls every exported function
against the real www.cihi.ca health workforce listing and workbooks (not mocks), per
AGENTS.md's "lesson from auditing the StatCan module".

It checks structure and relationships that hold whenever CIHI publishes a consistent
release, not figures: the nursing workbook is on the listing's second page, a physician
workbook's Ontario cells are marks rather than zeros, a mark is never turned into a number,
the same fact published in two workbooks agrees, and the French file reads like the English
one. Each workbook is downloaded once per run (cached for hours); the two biggest tables
(a 24.9 MB workbook with 204,000 rows on one sheet) take 20 to 40 s to scan.

Usage:
    uv run python scripts/smoke_test_cihi_workforce.py
"""

from __future__ import annotations

import asyncio
import sys

from maplestats_mcp.modules.cihi.workforce import client
from maplestats_mcp.shared.errors import InvalidInput, TooLarge

PHYSICIANS = "supply-distribution-migration-physicians-in-canada-2025-data-tables"
NURSING = "nursing-in-canada-2016-2025-data-tables"
PSW = "personal-support-workers-in-alberta-2025-data-tables"
NPDB = "npdb-utilization-data-tables-2024"
NPDB_HISTORY = "npdb-historical-utilization-2015-2024-data-tables"
NPDB_OVER_CAP = "npdb-historical-utilization-1996-2014-data-tables"


def check(ok: bool, label: str) -> bool:
    print(f"{'OK' if ok else 'FAIL'}: {label}")
    return ok


async def main() -> int:
    ok = True

    listed = await client.list_workbooks(include_earlier=True)
    ids = {w.id: w for w in listed.workbooks}
    ok &= check(len(ids) >= 40, f"list_workbooks -> {len(ids)} workbooks, newest first")
    ok &= check(NURSING in ids, "the nursing workbook (page 1 of the listing) is listed")
    topics = {w.topic for w in listed.workbooks}
    ok &= check(
        {"physicians", "nursing", "pharmacists", "physiotherapists"} <= topics,
        f"topics -> {sorted(topics)}",
    )
    ok &= check(
        all(
            w.url.startswith("https://www.cihi.ca/sites/default/files/document/")
            for w in ids.values()
        ),
        "every address is a file on www.cihi.ca",
    )
    quick = [w for w in ids.values() if w.kind == "interactive"]
    archives = [w for w in ids.values() if w.kind == "archive"]
    ok &= check(
        bool(quick) and bool(archives) and not any(w.readable for w in quick + archives),
        f"Quick Stats ({len(quick)}) and archives ({len(archives)}) listed but not readable",
    )
    current = await client.list_workbooks()
    ok &= check(current.returned_count < listed.returned_count, "earlier releases are hidden")
    french = await client.list_workbooks(query="pharmaciens", lang="fr")
    ok &= check(
        any("pharmaciens" in w.title.lower() for w in french.workbooks),
        f"French listing -> {[w.id for w in french.workbooks][:2]}",
    )
    ok &= check("software applications of any kind" in current.terms, "the terms are in the result")

    tables = await client.list_tables(PHYSICIANS)
    by_id = {t.table: t for t in tables.tables}
    ok &= check(
        len(by_id) >= 25 and "3.0" in by_id, f"list_tables -> {len(by_id)} physician tables"
    )
    ok &= check(
        {s.reason for s in tables.skipped} >= {"hidden", "interactive"},
        f"hidden and drop-down sheets skipped -> {[(s.sheet, s.reason) for s in tables.skipped]}",
    )
    ok &= check(
        bool(tables.citation and "CIHI" in tables.citation), f"citation -> {tables.citation}"
    )

    # Ontario's 2025 physician counts are withheld: the mark must come back as a mark.
    summary = await client.get_table(
        PHYSICIANS,
        "3.0",
        filters={"Specialty": "1.0 Family medicine"},
        columns=["Alberta", "Ontario"],
    )
    values = summary.rows[0].values
    ok &= check(
        isinstance(values["Alta."], float) and values["Ont."] == "—",
        f"physicians per 100,000, family medicine 2025 -> {values}",
    )
    ok &= check(
        any("delayed" in note for note in summary.notes) and summary.column_letters["Alta."] == "J",
        "the table's notes say the release was delayed; column letter J for Alberta",
    )
    caveats = " ".join(summary.provenance.caveats)
    ok &= check(
        summary.provenance.commercial_use == "not_allowed"
        and "express prior written authorization" in caveats,
        "provenance carries commercial_use=not_allowed and CIHI's terms",
    )

    # The same count in the supply table and the summary table of one workbook.
    supply = await client.get_table(
        PHYSICIANS, "1.0", filters={"Specialty": "1 Family medicine"}, columns=["Alta."]
    )
    headline = await client.get_table(
        PHYSICIANS, "A", filters={"Indicator": "Family medicine"}, columns=["Alta."], limit=5
    )
    ok &= check(
        supply.rows[0].values["Alta."] in [r.values["Alta."] for r in headline.rows],
        f"Alberta family medicine physicians agree across Tables 1.0 and A -> {supply.rows[0].values}",
    )

    # A percentage cell comes back as text, a mark as a mark (nursing Table 1).
    nurses = await client.get_table(
        NURSING,
        "1",
        filters={"Type of professional": "Registered nurses", "Category": "Supply"},
        columns=["Alberta"],
    )
    shown = {r.labels["Group"]: r.values["Alberta"] for r in nurses.rows}
    ok &= check(
        isinstance(shown["Total"], int) and str(shown["Percentage female"]).endswith("%"),
        f"nursing Table 1, Alberta registered nurses -> {shown}",
    )

    # An unknown filter value names the real ones instead of returning nothing.
    try:
        await client.get_table(NURSING, "3b", filters={"Jurisdiction": "Atlantis"})
        ok &= check(False, "an unknown jurisdiction is refused")
    except InvalidInput as exc:
        ok &= check("Alberta" in str(exc), "an unknown jurisdiction lists the real ones")

    # The same figure in two workbooks (NPDB 2024-2025 and its historical file).
    recent = await client.get_table(
        NPDB,
        "A.1",
        filters={"Section": "Family medicine", "Row label": "Major consultations"},
        columns=["Alta."],
    )
    history = await client.get_table(
        NPDB_HISTORY,
        "1",
        filters={
            "Fiscal year": "2024–2025",
            "Jurisdiction": "Alta.",
            "Specialty": "Family medicine",
            "NGS code": "1.0",
        },
        columns=["Number of services"],
    )
    ok &= check(
        recent.rows[0].values["Alta."] == history.rows[0].values["Number of services"],
        "NPDB services (Alberta, family medicine, major consultations) agree across two "
        f"workbooks -> {recent.rows[0].values['Alta.']}",
    )
    ok &= check(history.matching_rows == 1, "the 204,000-row sheet filtered to one row")

    # French: same cells, French names, "s.o." for not applicable.
    fr = await client.get_table(PSW, "1", columns=["2025"], lang="fr")
    ok &= check(
        fr.label_columns == ["Catégorie", "Groupe"] and fr.provenance.lang == "fr",
        f"French PSW table -> {fr.label_columns}, {list(fr.rows[0].values)}",
    )
    ok &= check(
        isinstance(fr.rows[0].values["Nombre 2025"], int),
        f"French thousands spaces read as numbers -> {fr.rows[0].values}",
    )

    notes = await client.get_notes(NURSING)
    ok &= check(
        any(s.sheet == "Definitions" for s in notes.sheets),
        f"notes -> {[s.sheet for s in notes.sheets]}",
    )

    # A workbook over the download cap is refused from its declared length, not read.
    try:
        await client.list_tables(NPDB_OVER_CAP)
        ok &= check(False, "a 40 MB workbook is refused")
    except TooLarge as exc:
        ok &= check("bytes" in str(exc), f"the 40 MB workbook is refused -> {str(exc)[:90]}")

    print("ALL OK" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
