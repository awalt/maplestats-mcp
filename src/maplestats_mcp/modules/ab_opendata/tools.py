"""MCP tools for the Open Alberta file reader."""

from __future__ import annotations

from typing import Literal

from fastmcp.tools import tool

from maplestats_mcp.modules.ab_opendata import client, constants
from maplestats_mcp.modules.ab_opendata.schemas import (
    ActivityIndex,
    BudgetTable,
    DatasetDetail,
    DatasetList,
    OrganizationList,
    PopulationProjection,
    ProjectionSummary,
    ResourceRows,
    ResourceStructure,
)

Lang = Literal["en", "fr"]
FormatName = Literal["xlsx", "xls", "csv"]
SortName = Literal["relevance", "modified", "title"]


@tool
async def ab_opendata_search_datasets(
    query: str | None = None,
    organization: str | None = None,
    format: FormatName | None = None,
    ogl_alberta_only: bool = False,
    sort: SortName = "relevance",
    limit: int = constants.DATASETS_LIMIT_DEFAULT,
    offset: int = 0,
    lang: Lang = "en",
) -> DatasetList:
    """Search Open Alberta (open.alberta.ca) datasets that have Excel or CSV files.

    Use for: finding the file behind an Alberta government number: AISH and Income
    Support caseloads, Alberta Health indicator tables, Treasury Board and Finance
    (economic review indicators at a glance, population projections), Education and
    post-secondary results, Municipal Affairs financial returns, energy royalties,
    traffic volumes and collisions, vital statistics (births, deaths). Each dataset
    shows title, ministry (organization), licence, last-modified date, update
    frequency and its resources with format, size and file URL (for
    ab_opendata_describe_resource and ab_opendata_read_resource). `query` is free
    text; `organization` is a slug (see ab_opendata_list_organizations); `format`
    keeps xlsx, xls or csv; `ogl_alberta_only` drops the rare dataset under another
    licence (those are flagged, with a plain note that other terms apply). The
    portal's DataStore has no active resources, so files are the only route to rows.
    `sort` modified or title, or an `offset`, drops the organization counts (portal limitation).
    Pace: one request per 10 seconds.
    Keywords: Open Alberta, Alberta government, open.alberta.ca, dataset search,
    Excel, CSV, AISH, Income Support, Alberta Health, Treasury Board and Finance,
    Open Government Licence Alberta, ministry.
    Mots-clés : Open Alberta, gouvernement de l'Alberta, données ouvertes Alberta,
    recherche de jeux de données, Excel, CSV, AISH, soutien du revenu, Alberta
    Health, Conseil du Trésor et Finances, Licence du gouvernement ouvert – Alberta,
    ministère.
    """
    return await client.search_datasets(
        query=query,
        organization=organization,
        format=format,
        ogl_alberta_only=ogl_alberta_only,
        sort=sort,
        limit=limit,
        offset=offset,
        lang=lang,
    )


@tool
async def ab_opendata_list_organizations(
    format: FormatName | None = None, lang: Lang = "en"
) -> OrganizationList:
    """List the Alberta ministries and agencies that publish Excel or CSV datasets.

    Use for: getting the organization slug (health, treasuryboardandfinance,
    education, municipalaffairs, energy-and-minerals, assisted-living-and-social-
    services, transportation-and-economic-corridors, servicealberta, advancededucation
    and others) to pass as `organization` to ab_opendata_search_datasets, with the
    number of datasets each has with files. Ministries are renamed after
    reorganizations, so older datasets can sit under a former name.
    Keywords: Open Alberta, organizations, ministries, departments, agencies, Alberta
    Health, Treasury Board and Finance, Education, Municipal Affairs, publishers,
    dataset counts.
    Mots-clés : Open Alberta, organisations, ministères, organismes, Alberta Health,
    Conseil du Trésor et Finances, Éducation, Affaires municipales, éditeurs, nombre
    de jeux de données, gouvernement de l'Alberta.
    """
    return await client.list_organizations(format=format, lang=lang)


@tool
async def ab_opendata_get_dataset(dataset: str, lang: Lang = "en") -> DatasetDetail:
    """Get one Open Alberta dataset with every resource, its licence and update cycle.

    Use for: seeing all the files of a dataset found by ab_opendata_search_datasets
    (yearly workbooks, CSV and XLSX copies of one table, former versions), each with
    format, size, last-modified date, whether this module can read it, and the
    licence. `dataset` is the slug, the dataset id, or the open.alberta.ca/dataset
    page URL. Files that are links to other sites (regional dashboard exports, maps,
    PDFs) are listed with readable false.
    Keywords: Open Alberta, dataset, resources, files, licence, update frequency,
    metadata, Excel, CSV, Alberta government, Open Government Licence.
    Mots-clés : Open Alberta, jeu de données, ressources, fichiers, licence, fréquence
    de mise à jour, métadonnées, Excel, CSV, gouvernement de l'Alberta, Licence du
    gouvernement ouvert.
    """
    return await client.get_dataset(dataset=dataset, lang=lang)


@tool
async def ab_opendata_describe_resource(
    url: str, sheet: str | None = None, lang: Lang = "en"
) -> ResourceStructure:
    """List the sheets and columns of an Open Alberta Excel or CSV file.

    Use for: looking inside a file before reading it: every sheet name with its
    declared row and column counts, the guessed header row, the column names and the
    first rows after the header. Many Alberta workbooks open with a notes or cover
    sheet, put title rows above the table or run years across columns, so check
    this before ab_opendata_read_resource. `url` is a resource URL from
    ab_opendata_search_datasets (a /dataset/<id>/resource/<id>/download/ link on
    open.alberta.ca); .xlsx, .xls and .csv are read, and the real format is detected
    from the file because the portal's labels are sometimes wrong. The result
    carries the licence and the attribution statement to cite. Pace: one request
    per 10 seconds.
    Keywords: Open Alberta, sheets, columns, header row, Excel, xlsx, xls, CSV, file
    structure, preview, workbook, Alberta government data.
    Mots-clés : Open Alberta, feuilles, colonnes, ligne d'en-tête, Excel, xlsx, xls,
    CSV, structure d'un fichier, aperçu, classeur, données du gouvernement de
    l'Alberta.
    """
    return await client.describe_resource(url=url, sheet=sheet, lang=lang)


@tool
async def ab_opendata_read_resource(
    url: str,
    sheet: str | None = None,
    columns: list[str] | None = None,
    filters: dict[str, str] | None = None,
    contains: str | None = None,
    header_row: int | None = None,
    header_rows: int = 1,
    limit: int = constants.ROWS_LIMIT_DEFAULT,
    offset: int = 0,
    lang: Lang = "en",
) -> ResourceRows:
    """Read rows of an Open Alberta Excel (.xlsx, .xls) or CSV file.

    Use for: getting the numbers: AISH and Income Support monthly caseloads, Alberta
    Health indicators by zone, population projections, post-secondary enrolment,
    municipal financial returns and tax rates, oil sands royalty and project data,
    highway traffic volumes, live births and deaths, wildfire records. `url` is a
    resource URL from ab_opendata_search_datasets. With several sheets and no
    `sheet`, the largest is read only when it holds most of the workbook (a notes
    sheet beside the table); otherwise no rows come back, only the sheet list, so
    pick one (same rule as ckan_read_resource). A CSV has no sheets: leave `sheet`
    unset. `header_row` is guessed (the first
    row with three filled cells) and can be set as a 1-based row number;
    `header_rows` (1 to 5) joins that many rows into the column names when a
    header spans several rows (years above labels, as in highway traffic
    volumes); layouts are kept as published, every value is text, and columns are named from the
    header (blank ones column_N). `columns` picks columns, `filters` keeps rows
    whose column equals the value exactly (case-insensitive, e.g. {"Zone":
    "Calgary"}), `contains` keeps rows with that text in any cell, and `offset` and
    `limit` page the result (total_rows counts every match). The result carries the
    licence and, for Open Government Licence - Alberta datasets, the attribution
    statement to cite. Pace: one request per 10 seconds.
    Keywords: Open Alberta, read file, Excel, xlsx, xls, CSV, rows, filter, caseload,
    population projections, traffic volume, royalties, wildfire, Alberta Health.
    Mots-clés : Open Alberta, lire un fichier, Excel, xlsx, xls, CSV, lignes, filtre,
    dossiers, projections de population, volume de circulation, redevances, feux de
    forêt, Alberta Health.
    """
    return await client.read_resource(
        url=url,
        sheet=sheet,
        columns=columns,
        filters=filters,
        contains=contains,
        header_row=header_row,
        header_rows=header_rows,
        limit=limit,
        offset=offset,
        lang=lang,
    )


@tool
async def ab_opendata_get_activity_index(
    start: str | None = None,
    end: str | None = None,
    last_n: int | None = None,
    lang: Lang = "en",
) -> ActivityIndex:
    """Get the Alberta Activity Index (AAX), Treasury Board and Finance's monthly index.

    Use for: the province's own monthly gauge of Alberta economic activity, January
    1981 = 100, from 1981 to the most recent month (about two months behind): a weighted
    average of nine indicators (employment, average weekly earnings, retail
    and wholesale trade, manufacturing, new truck sales, housing starts, rigs drilling,
    oil production). `start` and `end` are months as YYYY-MM; `last_n` keeps the
    last n months of that range. With none of them, the last 24 months come back.
    Values are the published index levels; recent months are revised. Read from the
    current file of the Open Alberta dataset alberta-activity-index-data-tables
    (Open Government Licence - Alberta; cite the attribution). For a quarterly or
    annual output figure use StatCan's wds_ tools; for the indicators themselves use
    ab_economic_ (Alberta Economic Dashboard). Pace: one request per 10 seconds.
    Keywords: Alberta Activity Index, AAX, Alberta economy, economic activity index,
    Alberta economic indicator, Treasury Board and Finance, Office of Statistics and
    Information, business cycle, nowcast.
    Mots-clés : indice d'activité de l'Alberta, AAX, économie albertaine, activité
    économique mensuelle, indicateur économique, Conseil du Trésor et Finances,
    conjoncture, cycle économique, substitut du PIB, Alberta.
    """
    return await client.get_activity_index(start=start, end=end, last_n=last_n, lang=lang)


@tool
async def ab_opendata_get_population_projection(
    geography: client.ProjectionGeography = "alberta",
    area: str | None = None,
    scenario: client.ScenarioName = "medium",
    gender: client.GenderName = "all",
    start_year: int | None = None,
    end_year: int | None = None,
    ages: bool = False,
    edition: int | None = None,
    lang: Lang = "en",
) -> PopulationProjection:
    """Get Alberta government population projections to 2051, for Alberta or an area.

    Use for: how many people Alberta, a census division, a CMA (Calgary, Edmonton,
    Lethbridge, Red Deer), an economic region, a local geographic area, a health zone
    area or a school authority is projected to have each year to 2051, from Treasury
    Board and Finance (Office of Statistics and Information), with StatCan
    estimates for 2001 up to the edition's first year (projected false). Alberta has
    low, medium and high scenarios; every sub-provincial geography is the medium
    scenario only. For a sub-provincial geography, `area` is a sheet of its workbook
    (census division codes 4801 to 4819, CMA names, ...): leave it unset first to get
    `areas` and no rows. `gender` is all (default), women+, men+ or any (all three).
    `start_year`/`end_year` trim the years; `ages=true` adds population by single year
    of age. `edition` is the first projection year (2024 onward); by default the
    newest edition found. Population on July 1. Open Government Licence - Alberta.
    For projected births and deaths use ab_opendata_get_population_projection_summary.
    Pace: one request per 10 seconds; a large workbook (local geographic areas, 6 MB)
    takes longer to open.
    Keywords: Alberta population projections, population forecast, demographic
    projection, 2051, census division, Calgary, Edmonton, scenario, age, Treasury
    Board and Finance, future population.
    Mots-clés : projections démographiques de l'Alberta, prévisions de population,
    population future, 2051, division de recensement, Calgary, Edmonton, scénario,
    âge, Conseil du Trésor et Finances.
    """
    return await client.get_population_projection(
        geography=geography,
        area=area,
        scenario=scenario,
        gender=gender,
        start_year=start_year,
        end_year=end_year,
        ages=ages,
        edition=edition,
        lang=lang,
    )


@tool
async def ab_opendata_get_population_projection_summary(
    start_year: int | None = None,
    end_year: int | None = None,
    edition: int | None = None,
    lang: Lang = "en",
) -> ProjectionSummary:
    """Get the summary of Alberta's population projections: growth and its components.

    Use for: Alberta's projected population to 2051 (medium scenario) with the
    percent change, men+ per 100 women+, average age, child and elderly dependency
    ratios, total fertility rate, median age at death, and the components of growth
    (births, deaths, immigrants, net emigrants, net non-permanent residents, net
    inflow from elsewhere in the country, total net inflow), as projected by Treasury
    Board and Finance (Office of Statistics and Information). Years before the edition's first
    projection year are StatCan estimates (projected false). Components
    cover the July-to-June period ending in that year (`period`). `edition` is the
    first projection year (2024 onward); by default the newest found. Open
    Government Licence - Alberta. For areas, ages or the low and high scenarios use
    ab_opendata_get_population_projection. Pace: one request per 10 seconds.
    Keywords: Alberta population projections, projected components of growth,
    projected births, projected deaths, fertility rate, dependency ratio, average age,
    population summary, 2051.
    Mots-clés : projections démographiques de l'Alberta, accroissement
    démographique, solde migratoire projeté, naissances, décès, indice
    de fécondité, rapport de dépendance, âge moyen, 2051.
    """
    return await client.get_population_projection_summary(
        start_year=start_year, end_year=end_year, edition=edition, lang=lang
    )


@tool
async def ab_opendata_get_budget_table(
    part: str | None = None,
    table: str | None = None,
    edition: int | None = None,
    contains: str | None = None,
    lang: Lang = "en",
) -> BudgetTable:
    """Get a table of the Alberta budget's fiscal plan: economic outlook, revenue, expense.

    Use for: the Alberta government's own budget figures and forecasts, Budget 2017
    to the latest: the Key Energy and Economic Assumptions (WTI and WCS oil prices,
    natural gas price, exchange rate, interest rates, real and nominal GDP, employment,
    unemployment rate, population, CPI inflation, housing starts) with actuals and
    forecasts, the economic outlook chart data, private forecasters' benchmarks,
    total revenue, resource royalties, tax revenue, operating expense by ministry,
    surplus or deficit, net debt, the capital plan, tax rates and interprovincial tax
    comparisons. Three steps, one request each: no `part` lists the workbooks
    (economic outlook, revenue, expense, capital plan, tax plan, other); a `part`
    lists its tables; `table` (a sheet name or words of its title, e.g.
    'KeyAssumptions', 'Total Revenue', 'Statement of Operations') reads it as labelled
    rows with figures by column ('2026-27 Estimate', '2025-26 Forecast').
    `contains` keeps rows whose label or heading has that text. `edition` is the
    budget year (2026 = fiscal plan 2026-29); default the latest. Open Government
    Licence - Alberta. Pace: one request per 10 seconds.
    Keywords: Alberta budget, fiscal plan, economic outlook, Treasury Board and
    Finance, deficit, revenue, royalties, oil price forecast, WTI assumption, expense.
    Mots-clés : budget de l'Alberta, plan financier, perspectives économiques,
    hypothèses économiques, prévision du prix du pétrole, déficit, revenus,
    redevances, dépenses, Conseil du Trésor et Finances.
    """
    return await client.get_budget_table(
        part=part, table=table, edition=edition, contains=contains, lang=lang
    )
