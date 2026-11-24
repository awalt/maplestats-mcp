"""MCP tools for the Saskatchewan Bureau of Statistics."""

from __future__ import annotations

from typing import Literal

from fastmcp.tools import tool

from maplestats_mcp.modules.sk_stats import client, constants
from maplestats_mcp.modules.sk_stats.schemas import FileList, FileRows

Lang = Literal["en", "fr"]


@tool
async def sk_stats_list_files(
    product: client.Product | None = None,
    query: str | None = None,
    kind: client.KindChoice = "data_table",
    limit: int = constants.FILES_LIMIT_DEFAULT,
    offset: int = 0,
    lang: Lang = "en",
) -> FileList:
    """List the Saskatchewan Bureau of Statistics' Excel tables and PDF reports.

    Use for: finding a Saskatchewan statistics file and its `format_id` for
    sk_stats_read_file. Products: economic_accounts (Saskatchewan Provincial
    Economic Accounts: GDP, household income, compensation of employees, 1988 on),
    economic_review (yearly Economic Review tables), monthly_review (Monthly
    Statistical Review), labour_force (labour force characteristics, monthly
    reports, Indigenous labour force), cpi (Consumer Price Index data and
    inflation reports), demography (quarterly population and components, by age
    and gender, population estimate reports), census (population by census
    division and community, 1986 on), fact_sheets. `kind` is data_table (default,
    the Excel files), document (PDF) or any; `query` keeps files whose title
    contains every word; no `product` lists all eight. Newest first; `limit`
    (default 40) and `offset` page. Crown copyright, non-commercial reproduction.
    Keywords: Saskatchewan, Saskatchewan Bureau of Statistics, SBS, provincial
    economic accounts, GDP, population, census division, labour force, CPI, Excel.
    Mots-clés : Saskatchewan, Bureau de la statistique de la Saskatchewan, comptes
    économiques provinciaux, PIB, population, division de recensement, population
    active, IPC, tableaux Excel.
    """
    return await client.list_files(
        product=product, query=query, kind=kind, limit=limit, offset=offset, lang=lang
    )


@tool
async def sk_stats_read_file(
    format_id: int,
    sheet: str | None = None,
    header_row: int | None = None,
    header_rows: int = 1,
    filters: dict[str, str] | None = None,
    contains: str | None = None,
    columns: list[str] | None = None,
    limit: int = constants.ROWS_LIMIT_DEFAULT,
    offset: int = 0,
    lang: Lang = "en",
) -> FileRows:
    """Read one sheet of a Saskatchewan Bureau of Statistics Excel file.

    Use for: the numbers in a table found with sk_stats_list_files (pass its
    `format_id`): Saskatchewan GDP and income accounts by year, quarterly
    population and its components (births, deaths, migration), population by age
    and gender, census population by community. Every sheet is listed with its
    size; a one-sheet file (or one sheet holding most of the cells) is read
    directly, otherwise no rows come back until `sheet` names one (the economic
    accounts have an index sheet and one sheet per table, "1.1", "2.3"). Layouts
    are kept as published: a title row above years across columns, notes at the
    bottom. `header_row` (1-based) overrides the guessed header, `header_rows`
    joins rows of a multi-row header, `filters` keeps rows whose column equals a
    value, `contains` keeps rows with that text in any cell, `columns` picks
    columns; values are text. Crown copyright, non-commercial reproduction.
    Keywords: Saskatchewan, Excel, sheet, workbook, xlsx, economic accounts,
    GDP, population components, census, table rows.
    Mots-clés : Saskatchewan, fichier Excel, feuille de calcul, classeur, lire un
    tableau, comptes économiques, PIB, composantes de la population, recensement.
    """
    return await client.read_file(
        format_id=format_id,
        sheet=sheet,
        header_row=header_row,
        header_rows=header_rows,
        filters=filters,
        contains=contains,
        columns=columns,
        limit=limit,
        offset=offset,
        lang=lang,
    )
