"""MCP tools for CRA's individual tax statistics (T1 Final Basic Tables, FSA tables)."""

from __future__ import annotations

from typing import Literal

from fastmcp.tools import tool

from maplestats_mcp.modules.cra_tax_stats import client
from maplestats_mcp.modules.cra_tax_stats.constants import ROWS_DEFAULT
from maplestats_mcp.modules.cra_tax_stats.schemas import (
    FsaSeries,
    FsaTable,
    T1Series,
    T1Table,
    TaxCatalogue,
)

Lang = Literal["en", "fr"]
Series = Literal["t1_final", "fsa"]
Measure = Literal["number", "amount"]
FsaTableCode = Literal["1a", "1b", "1c", "1d", "1e", "2"]


@tool
async def cra_tax_stats_list_tables(
    series: Series = "t1_final", tax_year: int | None = None, lang: Lang = "en"
) -> TaxCatalogue:
    """List the CRA individual tax statistics editions covered, and one edition's tables.

    Use for: finding which tax years and tables cra_tax_stats_ reads before
    asking for values. `series` is "t1_final" (the T1 Final Basic Tables,
    Individual Income Tax Return Statistics, tax years 2018-2024) or "fsa"
    (statistics by forward sortation area, tax years 2017-2021). Without
    `tax_year` it lists the editions and table titles; with one it reads that
    edition's package on open.canada.ca and lists the CSV files found (table,
    area, file link), which shows gaps such as a province file published only
    as a PDF. Keywords: CRA, Canada Revenue Agency, T1 final statistics,
    individual income tax return statistics, tax year, editions, tables,
    forward sortation area, FSA, income tax statistics.
    Mots-clés : ARC, Agence du revenu du Canada, statistiques finales T1,
    statistiques sur les déclarations des particuliers, année d'imposition,
    éditions, tableaux, région de tri d'acheminement, RTA, statistiques fiscales.
    """
    return await client.list_tables(series, tax_year, lang)


@tool
async def cra_tax_stats_get_t1_table(
    tax_year: int,
    table: int = 1,
    area: str = "ca",
    item: str | None = None,
    group: str | None = None,
    measure: Measure | None = None,
    limit: int = ROWS_DEFAULT,
    offset: int = 0,
    lang: Lang = "en",
) -> T1Table:
    """Read one T1 Final Basic Table (CRA income tax return statistics) for one tax year.

    Use for: number of tax filers, total income, deductions, taxable income,
    federal and provincial tax, and any T1 line item (employment income, RRSP
    deductions, capital gains, CPP contributions, charitable donations ...) by
    province, income class, source of income, or age and gender, tax years
    2018-2024. Tables: 1 general statement by province (returns, total
    income, deductions, taxable income, credits, federal, provincial and total
    tax; taxable, non-taxable and all returns); 2 line items by total income
    class; 3 by major source of income; 4 by age group and gender; 5 by
    province of residence. `area` is "ca" (all of Canada), a two-letter
    province code (on, qc, ab ...) or "nr" (non-residents); Tables 2 and 4
    (and 3 to 2021) have province files, Tables 1 and 5 only "ca". `item` and `group` filter by
    words in the label (or `item` by line number). Rows are long: one per item,
    group and measure (number of returns, or amount in thousands of dollars
    for every edition, with the unit the file published). Keywords: CRA, T1
    final statistics, income tax returns, tax filers, total income, taxable
    income, income class, income bracket, line items, deductions, tax payable.
    Mots-clés : ARC, statistiques finales T1, déclarations de revenus,
    déclarants, revenu total, revenu imposable, catégorie de revenu, tranche de
    revenu, postes, déductions, impôt à payer.
    """
    return await client.get_t1_table(
        tax_year, table, area, item, group, measure, limit, offset, lang
    )


@tool
async def cra_tax_stats_get_t1_series(
    table: int,
    item: str,
    group: str | None = None,
    area: str = "ca",
    return_type: str | None = "All returns",
    measure: Measure | None = None,
    from_year: int | None = None,
    to_year: int | None = None,
    lang: Lang = "en",
) -> T1Series:
    """Follow one T1 line item across tax years (CRA T1 Final Basic Tables, 2018-2024).

    Use for: a time series of a CRA income tax statistic, e.g. total income
    assessed, number of returns, RRSP deductions or capital gains, for Canada,
    one province, one income class or one age group, read from each yearly
    edition and put in the same units (thousands of dollars; Table 1 was
    published in millions to 2021). `item` is the exact label as
    cra_tax_stats_get_t1_table shows it ("Total income assessed", "Employment
    income"), case ignored; line numbers are not used because they shift
    between editions. `group` is the exact income class, age group or
    province ("Total" or "Canada" when omitted). `return_type` applies to
    Table 1 only ("All returns", "Taxable returns", "Non-taxable returns",
    or null for all three). Years where the label is not found are listed in
    missing_years. Keywords: CRA, T1 statistics, time series, trend, tax
    years, income tax, total income, tax filers, harmonized, editions.
    Mots-clés : ARC, statistiques T1, série chronologique, tendance, années
    d'imposition, impôt sur le revenu, revenu total, déclarants, harmonisé,
    éditions.
    """
    return await client.get_t1_series(
        table, item, group, area, return_type, measure, from_year, to_year, lang
    )


@tool
async def cra_tax_stats_get_fsa_table(
    tax_year: int,
    table: FsaTableCode = "1a",
    fsa: list[str] | None = None,
    province: str | None = None,
    item: str | None = None,
    limit: int = ROWS_DEFAULT,
    offset: int = 0,
    lang: Lang = "en",
) -> FsaTable:
    """Read CRA income tax statistics by forward sortation area (postal code area) for one year.

    Use for: tax filers and income for a neighbourhood or small area by the
    first three characters of its postal code (FSA, e.g. T5K, M5V, H2X), tax
    years 2017-2021. Tables: 1a returns, total, net and taxable income; 1b
    returns by total income class; 1c males and 1d females by income class;
    1e returns and amounts by source of income (employment, pension,
    investment, self-employment, benefits, other); 2 returns by age group.
    Filter with `fsa` (a list, up to 100) or `province` (two-letter code or
    SGC number); fsa=["Total"] with a province gives the province total.
    Amounts are in thousands of dollars for every year (CRA published whole
    dollars to 2020). Individual tax filers, not households: for household
    income use the census. Keywords: CRA, FSA, forward sortation area, postal code,
    neighbourhood income, tax filers, total income, small area income,
    income by postal code.
    Mots-clés : ARC, RTA, région de tri d'acheminement, code postal,
    déclarants, impôt des particuliers, revenu total par code postal, petites
    régions, statistiques fiscales locales, tranches d'âge.
    """
    return await client.get_fsa_table(tax_year, table, fsa, province, item, limit, offset, lang)


@tool
async def cra_tax_stats_get_fsa_series(
    fsa: str,
    table: FsaTableCode = "1a",
    item: str | None = None,
    from_year: int | None = None,
    to_year: int | None = None,
    lang: Lang = "en",
) -> FsaSeries:
    """Follow one forward sortation area's tax statistics across tax years (CRA, 2017-2021).

    Use for: how the number of tax filers or total income in one postal code
    area (FSA, e.g. T5K) changed from year to year, in the same units across
    editions (thousands of dollars; CRA switched from dollars to thousands in
    2021). `item` is the exact column label ("Total income", "Total"), case
    ignored; without it every column of the table is returned. FSA boundaries
    can change between years. Keywords: CRA, FSA, forward sortation area,
    postal code, income trend, tax filers, time series, neighbourhood,
    local income, total income.
    Mots-clés : ARC, RTA, région de tri d'acheminement, code postal,
    déclarants, série chronologique, évolution annuelle, impôt des
    particuliers, statistiques fiscales locales, années d'imposition.
    """
    return await client.get_fsa_series(fsa, table, item, from_year, to_year, lang)
