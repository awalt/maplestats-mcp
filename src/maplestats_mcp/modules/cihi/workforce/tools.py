"""MCP tools for CIHI's health workforce data tables."""

from __future__ import annotations

from typing import Literal

from fastmcp.tools import tool

from maplestats_mcp.modules.cihi.workforce import client, constants
from maplestats_mcp.modules.cihi.workforce.schemas import (
    TableRows,
    WorkbookList,
    WorkbookNotes,
    WorkbookTables,
)

Lang = Literal["en", "fr"]


@tool
async def cihi_workforce_list_workbooks(
    query: str | None = None, include_earlier: bool = False, lang: Lang = "en"
) -> WorkbookList:
    """List CIHI's health workforce data-table workbooks (physicians, nurses, pharmacists, ...).

    Use for: finding which CIHI workbook holds a health workforce figure: supply, distribution
    and migration of physicians, regulated nurses (RNs, LPNs, NPs, RPNs), pharmacists,
    physiotherapists, occupational therapists, personal support workers in Alberta, and the
    National Physician Database (physician services and payments). Each entry has CIHI's
    title, topic, publication date, its address and an id for cihi_workforce_list_tables.
    `query` keeps workbooks whose title, topic or description holds every word (English or
    French); earlier releases that a later one replaces are left out unless
    include_earlier=true. Quick Stats dashboards, .zip archives and workbooks in other layouts
    (COVID-19, surveys, virtual care) are listed with a `reason`, not read.
    CIHI's terms limit commercial use and use inside software applications without its
    written authorization: read `terms` and provenance.caveats before reusing any value.
    Keywords: CIHI, health workforce, physicians, nurses, nursing, pharmacists,
    physiotherapists, occupational therapists, personal support workers, health human
    resources, supply, workbooks.
    Mots-clés : ICIS, main-d'œuvre de la santé, médecins, infirmières, personnel infirmier,
    pharmaciens, physiothérapeutes, ergothérapeutes, préposés aux services de soutien à la
    personne, ressources humaines en santé, effectifs, classeurs.
    """
    return await client.list_workbooks(query=query, include_earlier=include_earlier, lang=lang)


@tool
async def cihi_workforce_list_tables(workbook: str, lang: Lang = "en") -> WorkbookTables:
    """List the tables of one CIHI workforce workbook: ids, titles, columns and cell ranges.

    Use for: seeing what a workbook from cihi_workforce_list_workbooks holds before reading
    it: each table's id ('3a', '1.0', 'A.1'), title, sheet, cell range, the label columns
    to filter on (jurisdiction, profession, specialty, year, age group, sex) and the value
    columns (years or jurisdictions across the top). Tables that repeat their header for
    each group list those groups as `sections`. Hidden helper sheets and drop-down (interactive)
    tabs are skipped and named in `skipped`; notes, definitions and methodology pages are
    in text_sheets (cihi_workforce_get_notes). `workbook` is an id or a distinctive name
    ("nursing", "pharmacists"); the first call downloads the file (0.1 to 27 MB; about 2 to
    10 s) and later calls are cached for hours. Workbooks over 30 MB are refused, not read.
    CIHI's terms limit commercial use and use inside software applications without its
    written authorization (see provenance.caveats).
    Keywords: CIHI, health workforce, table of contents, tables, sheets, columns,
    jurisdictions, specialties, age groups, workbook structure.
    Mots-clés : ICIS, main-d'œuvre de la santé, table des matières, tableaux, feuilles,
    colonnes, provinces et territoires, spécialités, groupes d'âge, structure du classeur.
    """
    return await client.list_tables(workbook=workbook, lang=lang)


@tool
async def cihi_workforce_get_table(
    workbook: str,
    table: str,
    filters: dict[str, str | list[str]] | None = None,
    contains: str | None = None,
    columns: list[str] | None = None,
    limit: int = constants.ROWS_DEFAULT,
    offset: int = 0,
    lang: Lang = "en",
) -> TableRows:
    """Read rows of one CIHI health workforce table by jurisdiction, profession, year or age.

    Use for: counts and rates of physicians, nurses, pharmacists, physiotherapists,
    occupational therapists and personal support workers: physicians per 100,000 population
    by specialty, the number of registered nurses (RNs, LPNs, nurse practitioners) by
    province and year, physician supply by age and sex, physicians moving between
    provinces, pharmacists employed in direct care, NPDB services and payments by
    specialty. Each row has its `labels`, its `values` by column and
    its sheet row (the cell is column_letters + row). A mark CIHI prints ('—' no data, 'n/a',
    'x' suppressed, 'n/r') comes back as that mark, never as zero or blank; a percentage cell
    comes back as text ('90.4%'); the table's own `notes` define the marks and say what is
    missing (in the 2025 physician tables the Ontario column, and so the Canada totals, is
    '—': data release delayed). `table` is
    an id from cihi_workforce_list_tables. `filters` match label columns exactly (case,
    accents and Alberta = Alta. = Alb. ignored; a list is any-of), e.g. {"Jurisdiction":
    "Alberta", "Year": "2024"}; `contains` is part of any label; `columns` picks value
    columns by name or part of a name (["Alberta", "Canada"], ["2025"]). 50 rows by default,
    500 at most, held to about 200 KB with the cut in provenance.limits. Large flat tables
    (200,000 rows) take 20 to 40 s to scan. CIHI's terms limit commercial use and use
    inside software applications without its written authorization: this server grants no
    licence; check them before reusing values (provenance.caveats).
    Keywords: CIHI, physicians per 100,000, registered nurses, number of nurses by
    province, regulated nurses, pharmacists supply, physiotherapists, occupational
    therapists, personal support workers, workforce by province, physician migration, NPDB,
    fee-for-service payments.
    Mots-clés : ICIS, médecins pour 100 000 habitants, personnel infirmier réglementé,
    infirmières autorisées, infirmières praticiennes, effectif de pharmaciens,
    physiothérapeutes, ergothérapeutes, préposés aux services de soutien à la personne,
    main-d'œuvre par province, migration des médecins, BDNM, paiements à l'acte.
    """
    return await client.get_table(
        workbook=workbook,
        table=table,
        filters=filters,
        contains=contains,
        columns=columns,
        limit=limit,
        offset=offset,
        lang=lang,
    )


@tool
async def cihi_workforce_get_notes(
    workbook: str, sheet: str | None = None, lang: Lang = "en"
) -> WorkbookNotes:
    """Read the instructions, methodology notes and definitions of a CIHI workforce workbook.

    Use for: CIHI's own wording on what a workforce figure means: how supply, workforce and
    employed in direct care are defined, who is included (regulated, licensed, registered),
    primary employment, the symbols used (— no data, n/a, x), which jurisdictions are
    missing and why, data sources (Health Workforce Database, Scott's Medical Database,
    National Physician Database), and how to cite the workbook. Without `sheet` the text
    pages come back (Instructions, Methodology notes, Definitions, Terminology); `sheet`
    keeps pages whose name contains it. Pages are cut to 60 paragraphs and 60,000 characters in
    all. CIHI's terms limit commercial use and use inside software applications without its
    written authorization (see provenance.caveats).
    Keywords: CIHI, methodology, definitions, terminology, how to cite, instructions,
    primary employment, direct care, regulated nurses, symbols, data sources.
    Mots-clés : ICIS, méthodologie, définitions, terminologie, comment citer, instructions,
    emploi principal, soins directs, personnel infirmier réglementé, symboles, sources de
    données.
    """
    return await client.get_notes(workbook=workbook, sheet=sheet, lang=lang)
