"""MCP tools for the Ontario Ministry of Finance population projections."""

from __future__ import annotations

from typing import Literal

from fastmcp.tools import tool

from maplestats_mcp.modules.on_finance import client, pages
from maplestats_mcp.modules.on_finance.schemas import (
    PageTables,
    PopulationProjection,
    ProjectionComponents,
)

Lang = Literal["en", "fr"]


@tool
async def on_finance_get_population_projection(
    geography: client.Geography = "ontario",
    area: str | None = None,
    scenario: client.ScenarioChoice = "reference",
    gender: client.GenderChoice = "all",
    start_year: int | None = None,
    end_year: int | None = None,
    age_groups: client.AgeGroups | None = None,
    release: client.Release = "latest",
    lang: Lang = "en",
) -> PopulationProjection:
    """Get Ontario Ministry of Finance population projections to 2051, by area and age.

    Use for: how many people Ontario, one of its 6 regions (Greater Toronto Area,
    Central, East, Southwest, Northeast, Northwest), 49 census divisions (Toronto,
    Peel, York, Ottawa, Hamilton, Waterloo...), 34 public health units or 9 MCCSS
    service delivery regions is projected to have each July 1 to 2051. Ontario has
    reference, low-growth and high-growth scenarios (`scenario`, or any); every other
    geography is the reference scenario. `area` is a name or region code; without it
    every area of the geography comes back (`areas` lists them). `gender` is all
    (default), women+, men+ or any; `start_year`/`end_year` trim the years.
    `age_groups` adds broad (0-14, 15-64, 65+), five_year or single_year counts
    (five_year and single_year need one area). `release` latest (default) takes the
    fall interim update where there is one (Ontario only), annual the summer release
    for every geography. Base year is a StatCan estimate. Open Government Licence -
    Ontario.
    Keywords: Ontario population projections, Ministry of Finance, population
    forecast, 2051, census division, public health unit, GTA, scenario, age groups.
    Mots-clés : projections démographiques de l'Ontario, ministère des Finances,
    population future, 2051, division de recensement, bureau de santé publique,
    région du grand Toronto, scénario, groupes d'âge.
    """
    return await client.get_population_projection(
        geography=geography,
        area=area,
        scenario=scenario,
        gender=gender,
        start_year=start_year,
        end_year=end_year,
        age_groups=age_groups,
        release=release,
        lang=lang,
    )


@tool
async def on_finance_get_projection_components(
    scenario: client.ScenarioChoice = "reference",
    start_year: int | None = None,
    end_year: int | None = None,
    release: client.Release = "latest",
    lang: Lang = "en",
) -> ProjectionComponents:
    """Get the projected components of Ontario's population change to 2051.

    Use for: the Ontario Ministry of Finance's projected births, deaths, natural
    increase, immigration, emigration, net change in non-permanent residents, net
    international migration, interprovincial in- and out-migration, net migration,
    total change and growth rate for each July-to-June period to 2050-51, with the
    starting population, under the reference, low-growth or high-growth scenario
    (`scenario`, or any for all three). `start_year`/`end_year` keep periods
    starting in those years. `release` latest (default) reads the fall interim
    update, annual the summer release. Open Government Licence - Ontario. For the
    projected population by area, gender and age use
    on_finance_get_population_projection.
    Keywords: Ontario population projections, components of growth, projected births,
    deaths, immigration, emigration, non-permanent residents, interprovincial
    migration.
    Mots-clés : projections démographiques de l'Ontario, composantes de
    l'accroissement, naissances, décès, immigration, résidents non permanents,
    migration interprovinciale, solde migratoire.
    """
    return await client.get_projection_components(
        scenario=scenario, start_year=start_year, end_year=end_year, release=release, lang=lang
    )


@tool
async def on_finance_get_page_tables(
    page: pages.PageName = "economic_accounts",
    table: str | None = None,
    lang: Lang = "en",
) -> PageTables:
    """Get the tables of the Ontario Economic Accounts or the Ontario Fact Sheet.

    Use for: Ontario's quarterly real and nominal GDP growth from the Ministry of
    Finance's Ontario Economic Accounts (summary, GDP by expenditure, by income,
    implicit price indexes, real GDP by industry, external factors such as US GDP,
    WTI oil and the exchange rate, and the release calendar), or the Ontario Fact
    Sheet's headline figures (population and share of Canada, urban areas, labour
    force, employment, unemployment and participation rates, GDP and household
    income, top export markets, exports and imports). `page` is economic_accounts
    (default) or fact_sheet; `table` keeps tables whose caption or heading contains
    that text ('1.5', 'industry', 'export'). Cells come as published, with the same
    cells read as numbers ('(0.3)' is -0.3). `lang=fr` reads the French page. Crown
    copyright: non-commercial reproduction, unchanged. For the source series use
    wds_.
    Keywords: Ontario Economic Accounts, Ontario GDP growth, quarterly GDP, Ontario
    Fact Sheet, Ontario economy, Ministry of Finance, real GDP by industry, exports.
    Mots-clés : comptes économiques de l'Ontario, croissance du PIB de l'Ontario, PIB
    trimestriel, profil de l'Ontario, économie ontarienne, ministère des Finances,
    PIB réel par industrie, exportations.
    """
    return await pages.get_page_tables(page=page, table=table, lang=lang)
