"""MCP tools for the Manitoba Bureau of Statistics."""

from __future__ import annotations

from typing import Literal

from fastmcp.tools import tool

from maplestats_mcp.modules.mb_stats import client, constants
from maplestats_mcp.modules.mb_stats.schemas import FileData, FileList, IndicatorList

Lang = Literal["en", "fr"]


@tool
async def mb_stats_list_indicators(
    category: str | None = None,
    query: str | None = None,
    lang: Lang = "en",
) -> IndicatorList:
    """List the Manitoba Bureau of Statistics' headline indicators with their latest values.

    Use for: the latest Manitoba figure the Manitoba statistics bureau reports, as
    shown on its home page: population estimate, net interprovincial and international
    migration, natural increase, persons employed, unemployment rate, average weekly
    earnings, job vacancies, consumer price index, retail and wholesale trade,
    manufacturing sales, international trade balance, new motor vehicle sales,
    building permits, housing starts, business and consumer insolvencies, farm cash
    receipts, real and nominal GDP and the Manitoba Finance survey of forecasts. Each
    indicator has its reference period, value with units, change and its context
    (month to month, year to date), and `files` counts its tables in
    mb_stats_list_files (pass its `id` as `indicator`). `category` and `query` narrow
    the list. Most values repackage Statistics Canada releases. OpenMB licence.
    Keywords: Manitoba, Manitoba Bureau of Statistics, MBS, economic indicators,
    Winnipeg, population, unemployment, CPI, retail, quick facts.
    Mots-clés : Manitoba, Bureau des statistiques du Manitoba, indicateurs économiques,
    population, chômage, IPC, commerce de détail, mises en chantier, insolvabilités.
    """
    return await client.list_indicators(category=category, query=query, lang=lang)


@tool
async def mb_stats_list_files(
    query: str | None = None,
    indicator: int | None = None,
    kind: client.KindChoice = "data_table",
    limit: int = constants.FILES_LIMIT_DEFAULT,
    offset: int = 0,
    lang: Lang = "en",
) -> FileList:
    """List the Manitoba Bureau of Statistics' Excel tables, bulletins and reports.

    Use for: finding a Manitoba statistics table and its URL for mb_stats_read_file:
    retail and wholesale trade, manufacturing, building construction investment,
    labour force characteristics (Manitoba beside Canada, ten and twenty
    years), quarterly demographic statistics and migration, population estimates,
    CPI, exports and imports by country (United States, China, Japan, Mexico) and
    commodity, insolvencies. `kind` is data_table (default, the Excel files),
    document (PDF bulletins, the MBS Weekly, reports, infographics, provincial
    electoral division profiles), link (Statistics Canada tables) or any.
    `indicator` keeps files listed under one indicator id from
    mb_stats_list_indicators; `query` keeps files whose title contains every word.
    Newest first; `limit` (default 40) and `offset` page. OpenMB licence.
    Keywords: Manitoba, Manitoba Bureau of Statistics, Excel, xlsx, labour force,
    trade by country, demographic statistics, bulletin, MBS Weekly.
    Mots-clés : Manitoba, Bureau des statistiques du Manitoba, tableaux Excel,
    population active, exportations par pays, statistiques démographiques, bulletin,
    commerce de détail.
    """
    return await client.list_files(
        query=query, indicator=indicator, kind=kind, limit=limit, offset=offset, lang=lang
    )


@tool
async def mb_stats_read_file(
    url: str,
    sheet: str | None = None,
    contains: str | None = None,
    header_row: int | None = None,
    header_rows: int = 1,
    limit: int = constants.ROWS_LIMIT_DEFAULT,
    offset: int = 0,
    lang: Lang = "en",
) -> FileData:
    """Read one sheet of a Manitoba Bureau of Statistics Excel table.

    Use for: the numbers in a table found with mb_stats_list_files: Manitoba retail
    trade by industry, Manitoba beside Canada over ten years, Manitoba
    exports to a country by commodity, quarterly population and migration, labour
    force by age and gender. Layouts are kept as published: a title row comes first
    and headers can span rows (month, then year, then units), so `header_row` is a
    guess (the first row with three filled cells) you can override with a 1-based row
    number, and `header_rows` (1 to 5) joins that many rows per column. Every value is
    text. `contains` keeps rows with that text in any cell (an industry, a year, a
    region code); `offset` and `limit` page. Without `sheet`, the first sheet.
    Keywords: Manitoba, Excel, sheet, table, retail trade, exports, population,
    labour force, Winnipeg, xlsx.
    Mots-clés : Manitoba, fichier Excel, feuille de calcul, lire un tableau, commerce
    de détail, exportations, population, population active, Winnipeg.
    """
    return await client.read_file(
        url=url,
        sheet=sheet,
        contains=contains,
        header_row=header_row,
        header_rows=header_rows,
        limit=limit,
        offset=offset,
        lang=lang,
    )
