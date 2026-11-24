"""Live smoke test for modules/cihi/workforce's client.py: calls every exported function
against the real www.cihi.ca health workforce listing and workbooks (not mocks), per
AGENTS.md's "lesson from auditing the StatCan module".

It checks structure and relationships that hold whenever CIHI publishes a consistent
release, not figures: the nursing workbook is on the listing's second page, a physician
workbook's Ontario cells are marks rather than zeros, a mark is never turned into a number,
the same fact published in two workbooks agrees, and the French file reads like the English
one. Files over the 30 MiB cap are read by parts with range requests (a workbook of a .zip
archive, the 40.3 MB NPDB 1996-2014 workbook without its 239 MB Table 1). Each workbook is
downloaded once per run (cached for hours); the two biggest tables (a 24.9 MB workbook with
204,000 rows on one sheet) take 20 to 40 s to scan.

Usage:
    uv run python scripts/smoke_test_cihi_workforce.py
"""

from __future__ import annotations

import asyncio
import sys

from maplestats_mcp.modules.cihi.workforce import client
from maplestats_mcp.shared.errors import InvalidInput

PHYSICIANS = "supply-distribution-migration-physicians-in-canada-2025-data-tables"
NURSING = "nursing-in-canada-2016-2025-data-tables"
PSW = "personal-support-workers-in-alberta-2025-data-tables"
NPDB = "npdb-utilization-data-tables-2024"
NPDB_HISTORY = "npdb-historical-utilization-2015-2024-data-tables"
NPDB_OVER_CAP = "npdb-historical-utilization-1996-2014-data-tables"
QUICK_STATS = "health-workforce-quickstats-2024-data-tables"
PHYSICIANS_2023 = "supply-distribution-migration-physicians-in-canada-2023-data-tables"
NPDB_2022 = "npdb-payments-data-tables-2022"
NPDB_PAYMENTS_HISTORY = "npdb-historical-payments-1999-2024-data-tables"
COVID_WORKERS = "covid-19-health-care-worker-cases-deaths-march-2022-data-tables"
CMWF = "cmwf-2022-data-tables"
CMWF_QUICK = "cmwf-2022-quick-stats"
PROVIDERS = "canada-health-care-providers-2016-2020-data-tables"
PHARMACISTS = "pharmacists-in-canada-2016-2025-data-tables"


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
    inside = [w for w in ids.values() if w.archive]
    ok &= check(
        bool(quick) and all(w.readable for w in quick),
        f"Quick Stats ({len(quick)}) are read for their data sheets",
    )
    ok &= check(
        len(archives) == 2
        and not any(w.readable for w in archives)
        and len(inside) >= 6
        and all(w.edition == "earlier" for w in inside),
        f"archives listed by their workbooks -> {[(w.id, w.readable) for w in inside]}",
    )
    unread = [w.id for w in ids.values() if not w.readable and w.kind != "archive"]
    ok &= check(
        unread == ["npdb-historical-utilization-1996-2012-data-tables"],
        f"the only workbook not read is the 34.7 MB one inside the NPDB archive -> {unread}",
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
        {s.reason.split(":")[0] for s in tables.skipped} >= {"hidden", "interactive"},
        f"helper and drop-down sheets skipped -> {[s.sheet for s in tables.skipped]}",
    )
    ok &= check(
        "Supply" in by_id and by_id["Supply"].hidden_sheet,
        "the hidden Supply sheet behind the Table B drop-down is a table",
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

    # The hidden Supply sheet holds what the drop-down shows: Table A agrees with it.
    hidden = await client.get_table(
        PHYSICIANS,
        "Supply",
        filters={"Year": "2025", "Jurisdiction": "Alberta", "Specialty": "Physician supply"},
        columns=["Number of physicians"],
    )
    total = await client.get_table(
        PHYSICIANS, "A", filters={"Indicator": "All physicians"}, columns=["Alta."], limit=1
    )
    ok &= check(
        hidden.rows[0].values["Number of physicians"] == total.rows[0].values["Alta."],
        f"Supply (hidden) and Table A agree on Alberta's physicians -> {hidden.rows[0].values}",
    )

    # Quick Stats: the data sheet behind the dashboards agrees with the nursing workbook.
    flow = await client.get_table(
        QUICK_STATS,
        "Supply_WF_Flow",
        filters={
            "Year": "2024",
            "Province/Territory": "Alberta",
            "Type of provider": "Registered nurses",
        },
        columns=["Supply: number of providers"],
    )
    registered = await client.get_table(
        NURSING,
        "3a",
        filters={
            "Type of professional": "Registered nurses",
            "Jurisdiction": "Alberta",
            "Category": "Supply",
            "Group": "Total",
        },
        columns=["2024"],
    )
    ok &= check(
        flow.rows[0].values["Supply: number of providers"] == registered.rows[0].values["2024"],
        f"Quick Stats and Nursing Table 3a agree on Alberta's 2024 RNs -> {flow.rows[0].values}",
    )

    # Workbooks of the .zip archives, read by ranges, agree with the current releases.
    archived = await client.get_table(
        PHYSICIANS_2023, "1.0", contains="All physicians", columns=["Alta."]
    )
    later = await client.get_table(
        PHYSICIANS,
        "Supply",
        filters={"Year": "2023", "Jurisdiction": "Alberta", "Specialty": "Physician supply"},
        columns=["Number of physicians"],
    )
    ok &= check(
        archived.rows[0].values["Alta."] == later.rows[0].values["Number of physicians"]
        and "#" in archived.workbook_url,
        f"2023 physicians (archive) and the 2025 Supply sheet agree -> {archived.rows[0].values}",
    )
    payments = await client.get_table(
        NPDB_2022, "A.2.1", filters={"Specialty": "Total physicians"}, columns=["Alta."]
    )
    paid = await client.get_table(
        NPDB_PAYMENTS_HISTORY,
        "1",
        filters={
            "Fiscal year": "2022–2023",
            "Jurisdiction": "Alta.",
            "Indicator": "Total clinical payments",
            "Specialty": "Total physicians",
        },
        columns=["Payment"],
    )
    thousands = payments.rows[0].values["Alta."]
    payment = paid.rows[0].values["Payment"]
    ok &= check(
        isinstance(thousands, float)
        and isinstance(payment, float)
        and abs(thousands * 1000 - payment) < 1,
        f"NPDB 2022 payments (archive, $ thousands) agree with the history -> {thousands}",
    )

    # Over the cap: read by parts, the 239 MB Table 1 left out with its size.
    by_parts = await client.list_tables(NPDB_OVER_CAP)
    left_out = {s.sheet: s.reason for s in by_parts.skipped}
    ok &= check(
        [t.table for t in by_parts.tables] == ["2", "3"]
        and left_out.get("Table 1", "").startswith("too large: 418,139 rows"),
        f"the 40.3 MB workbook is read by parts -> {left_out.get('Table 1', '')[:70]}",
    )
    reciprocal = await client.get_table(
        NPDB_OVER_CAP,
        "2",
        filters={
            "Fiscal year": "2014–2015",
            "Report breakdown": "Summary",
            "Type of practice": "Total physicians",
            "Type of service": "Total services",
            "Host provider": "P.E.I.",
            "Home of patient": "N.L.",
        },
        columns=["Number of services"],
    )
    ok &= check(
        reciprocal.matching_rows == 1
        and isinstance(reciprocal.rows[0].values["Number of services"], int),
        f"reciprocal billing 2014-2015 (Table 2) -> {reciprocal.rows[0].values}",
    )

    # Layouts read since 2026-11-24: a banner over the header and zero-width spaces, survey
    # questions, and the 2016-2020 provider tables.
    workers = await client.get_table(COVID_WORKERS, "4", filters={"Province/territory": "N.S."})
    ok &= check(
        workers.rows[0].values["Total number of cases of COVID-19"] == 1067
        and workers.label_columns == ["Province/territory"],
        f"COVID-19 health care workers, N.S. (a zero-width space in the cell) -> "
        f"{workers.rows[0].values}",
    )
    survey = await client.get_table(CMWF, "Q68", filters={"Country": "Canada"})
    quick_survey = await client.get_table(CMWF_QUICK, "3", filters={"Country": "Canada"})
    ok &= check(
        survey.rows[0].values == quick_survey.rows[0].values,
        f"Commonwealth Fund Q68 and its Quick Stats Table 3 agree -> {survey.rows[0].values}",
    )
    providers = await client.get_table(
        PROVIDERS,
        "9",
        filters={"Type of provider": "Pharmacists", "Year": "2020"},
        columns=["Count"],
    )
    pharmacists = await client.get_table(
        PHARMACISTS,
        "3a",
        filters={"Jurisdiction": "Alberta", "Category": "Supply", "Group": "Total"},
        columns=["2020"],
    )
    ok &= check(
        providers.rows[0].values["Count Alberta"] == pharmacists.rows[0].values["2020"],
        f"2016-2020 providers and Pharmacists Table 3a agree on Alberta 2020 -> "
        f"{providers.rows[0].values}",
    )

    print("ALL OK" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
