"""MCP tools for the Census GeoSuite (92-150-X) tables, 1996 to 2021."""

from __future__ import annotations

from typing import Literal

from fastmcp.tools import tool

from maplestats_mcp.modules.statcan.geosuite import client, constants
from maplestats_mcp.modules.statcan.geosuite.schemas import (
    GeoSuiteQueryResult,
    GeoSuiteTableDescription,
    GeoSuiteTableList,
)
from maplestats_mcp.modules.statcan.lang import use_lang

GeoSuiteYear = Literal[1996, 2001, 2006, 2011, 2016, 2021]
Lang = Literal["en", "fr"]


@tool
async def statcan_geosuite_list_tables(
    year: GeoSuiteYear = 2016, lang: Lang = "en"
) -> GeoSuiteTableList:
    """List the Census GeoSuite tables of one census year (1996-2021) with sizes and sources.

    Use for: which census geography tables exist for a year before querying
    one: provinces (PR), census divisions (CD), subdivisions (CSD),
    consolidated subdivisions (CCS), CMAs and CAs (CMA_CA), census tracts
    (CT), dissemination areas (DA) and blocks (DB; 1996 has enumeration
    areas, EA, instead), economic regions (ER), federal electoral districts
    (FED), designated places (DPL), population centres (POPCTR), place names
    (PN) and the type code lists, with each table's title, row and column
    counts and file size, plus the year's StatCan source file, licence and
    attribution line. Statistics Canada's GeoSuite (92-150-X), read from
    MountainMath's Parquet re-host because StatCan's own copy is behind a
    Cloudflare bot challenge; provenance.caveats says so and how it was
    checked. For 2021 census values by geography use statcan_census_profile_.
    Keywords: GeoSuite, census geography, 2016 census, geographic codes,
    census subdivision, census tract, dissemination area, dissemination
    block, geographic attribute file, hierarchy.
    Mots-clés : GéoSuite, géographie du recensement, recensement de 2016,
    codes géographiques, subdivision de recensement, secteur de
    recensement, aire de diffusion, îlot de diffusion, fichier des
    attributs géographiques, hiérarchie géographique.
    """
    use_lang(lang)
    return await client.list_tables(year, lang)


@tool
async def statcan_geosuite_describe_table(
    year: GeoSuiteYear, table: str, lang: Lang = "en"
) -> GeoSuiteTableDescription:
    """Describe one Census GeoSuite table: columns, types, labels and sample rows.

    Use for: what a GeoSuite table's columns mean before filtering it (e.g.
    2016 CSD: CSDUID, CSDNAME, CSDTYPE, SACTYPE, CSDPOP2016, CSDTDWELL2016,
    CSDAREA2016, representative point latitude and longitude, PRUID, CDCODE,
    CMAUID...): each column's type, label, code meanings, notes, StatCan's
    source field name and coordinate system, the primary key, the notes on
    adjusted (A) and corrected (C) counts, three sample rows, and how the
    re-host compared the table with StatCan's file. `table` is a name from
    statcan_geosuite_list_tables (CSD, DA, DB...); the file (up to 15 MB) is
    downloaded once and kept.
    Keywords: GeoSuite, data dictionary, columns, census geography, field
    names, CSDUID, DAUID, DBUID, attribute file, record layout.
    Mots-clés : GéoSuite, dictionnaire de données, colonnes, géographie du
    recensement, nom des champs, identificateur unique, fichier des
    attributs, disposition des enregistrements, IDUGD.
    """
    use_lang(lang)
    return await client.describe_table(year, table, lang)


@tool
async def statcan_geosuite_query(
    year: GeoSuiteYear,
    table: str,
    filters: dict[str, list[str] | str] | None = None,
    name_contains: str | None = None,
    columns: list[str] | None = None,
    limit: int = constants.LIMIT_DEFAULT,
    offset: int = 0,
    lang: Lang = "en",
) -> GeoSuiteQueryResult:
    """Rows of one Census GeoSuite table (1996-2021), filtered by codes or a name.

    Use for: 2016 (and 1996-2021) census geography lookups: a place's codes
    and unique IDs (CSDUID, CDUID, CTUID, DAUID, DBUID), its name in English
    and French, the hierarchy above it (province, CD, CSD, CMA, tract) and
    its population, dwelling counts and land area for that census, e.g.
    every CSD of Ontario (table='CSD', filters={'PRUID': ['35']}), Toronto
    (filters={'CSDUID': ['3520005']}) or names containing 'montreal'
    (name_contains, case- and accent-insensitive, over the columns ending
    in NAME and the DESCEN/DESCFR of type tables). filters match a column's
    text exactly (any of the values given, case-insensitive); a value ending
    in * matches a prefix, e.g. a DA's blocks: table='DB',
    filters={'DBUID': ['35204831*']}. Small units carry their parents' codes
    (PRUID, CDCODE, CSDCODE, DACODE, CTNAME, CMAUID), not full parent UIDs.
    Column names are checked against the table and an unknown one is
    refused with the list. Rows come in primary-key order; total_matched counts them all,
    limit (up to 1,000) and offset page through. Run
    statcan_geosuite_describe_table for column meanings. 2021 values by
    characteristic: statcan_census_profile_.
    Keywords: GeoSuite, census geography lookup, 2016 census subdivision,
    dissemination area population, dissemination block, census tract,
    geographic code, CSDUID, population and dwelling counts, land area.
    Mots-clés : GéoSuite, recherche géographique du recensement,
    subdivision de recensement 2016, population de l'aire de diffusion,
    îlot de diffusion, secteur de recensement, code géographique, chiffres
    de population et des logements, superficie des terres.
    """
    use_lang(lang)
    return await client.query(year, table, filters, name_contains, columns, limit, offset, lang)
