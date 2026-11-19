"""MCP tools for City of Calgary open data: building permits and community populations."""

from __future__ import annotations

from typing import Literal

from fastmcp.tools import tool

from maplestats_mcp.modules.calgary import client
from maplestats_mcp.modules.calgary.schemas import (
    BuildingPermitList,
    BuildingPermitSummary,
    CommunityPopulationList,
    DateField,
    PermitGroupBy,
    PopulationBy,
)

Lang = Literal["en", "fr"]


@tool
async def calgary_list_building_permits(
    community: str | None = None,
    permit_class_group: str | None = None,
    work_class_group: str | None = None,
    status: str | None = None,
    permit_type: str | None = None,
    date_field: DateField = "issued",
    start_date: str | None = None,
    end_date: str | None = None,
    address_contains: str | None = None,
    min_housing_units: int | None = None,
    limit: int = 50,
    offset: int = 0,
    lang: Lang = "en",
) -> BuildingPermitList:
    """List Calgary building permits, newest first by date_field:
    permit number, status, applied/issued/completed dates, permit class,
    work class, description, applicant, contractor, dwelling units added,
    estimated project cost (dollars), floor area, address, community and
    WGS84 latitude/longitude. Every application since 1999, refreshed daily.

    community is the name ("BRIDGELAND/RIVERSIDE") or code ("BRD").
    permit_class_group ("Single Family", "Apartment"...), work_class_group
    ("New", "Improvement", "Demolition"), status and permit_type match
    exactly, ignoring case (calgary_summarize_building_permits lists the
    labels). start_date/end_date (inclusive YYYY-MM-DD) apply to
    date_field. address_contains: e.g. "17 AV SW". limit 1-500.
    Use for: Calgary permits issued on a street or in a Calgary community,
    who is building where in Calgary.
    Keywords: Calgary, Calgary building permits, permit records, permit
    applications, renovation, demolition, contractor, applicant, address,
    Calgary community.
    Mots-clés : Calgary, permis de bâtir à Calgary, demandes de permis,
    dossiers de permis, rénovation, démolition, entrepreneur, demandeur,
    adresse, quartier de Calgary.
    """
    return await client.list_building_permits(
        community=community,
        permit_class_group=permit_class_group,
        work_class_group=work_class_group,
        status=status,
        permit_type=permit_type,
        date_field=date_field,
        start_date=start_date,
        end_date=end_date,
        address_contains=address_contains,
        min_housing_units=min_housing_units,
        limit=limit,
        offset=offset,
        lang=lang,
    )


@tool
async def calgary_summarize_building_permits(
    group_by: PermitGroupBy = "community",
    community: str | None = None,
    permit_class_group: str | None = None,
    work_class_group: str | None = None,
    status: str | None = None,
    permit_type: str | None = None,
    date_field: DateField = "issued",
    start_date: str | None = None,
    end_date: str | None = None,
    address_contains: str | None = None,
    min_housing_units: int | None = None,
    top: int = 100,
    lang: Lang = "en",
) -> BuildingPermitSummary:
    """Count Calgary building permits, with the dwelling units they add
    and their estimated project cost (dollars), grouped by "community",
    "permit_class_group", "permit_class" (residential or not),
    "work_class_group", "permit_type", "status", "year" or "month", with
    the filters of calgary_list_building_permits. Sums cover every
    matching permit. Years and months follow date_field, oldest first,
    the most recent top (1-500) of them; other groupings come largest
    first. Also shows the exact labels to filter on.
    Use for: Calgary permits issued per month, dwelling units permitted by
    Calgary community, Calgary permit values by year.
    Keywords: Calgary, Calgary building permits, permit counts, permitted
    units, permit value, estimated cost, monthly permits, permit class,
    Calgary community.
    Mots-clés : Calgary, permis de bâtir à Calgary, nombre de permis,
    logements autorisés, valeur des permis, coût estimé, permis par mois,
    catégorie de permis, quartier de Calgary.
    """
    return await client.summarize_building_permits(
        group_by,
        community=community,
        permit_class_group=permit_class_group,
        work_class_group=work_class_group,
        status=status,
        permit_type=permit_type,
        date_field=date_field,
        start_date=start_date,
        end_date=end_date,
        address_contains=address_contains,
        min_housing_units=min_housing_units,
        top=top,
        lang=lang,
    )


@tool
async def calgary_get_community_populations(
    community: str | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
    by: PopulationBy = "community",
    limit: int = 100,
    offset: int = 0,
    lang: Lang = "en",
) -> CommunityPopulationList:
    """Population, occupied dwellings and persons per dwelling of Calgary's
    communities from Calgary's own civic census, 1968-2019, newest year
    first. Calgary held no civic census after 2019.

    community is the community name ("BRIDGELAND/RIVERSIDE") or its
    three-letter code ("BRD"); leave it out for every community.
    start_year/end_year bound the census years. by="total" sums the
    communities for each year instead (residual sub-areas left out, so it
    can differ slightly from the official civic census total). limit is
    1-1000; page with offset.
    Use for: how a Calgary community's population changed, Calgary civic
    census history by community.
    Keywords: Calgary, civic census, Calgary municipal census, Calgary
    community population, Calgary neighbourhoods, occupied dwellings,
    persons per unit, 1968-2019.
    Mots-clés : Calgary, recensement municipal de Calgary, population par
    quartier, quartiers de Calgary, logements occupés, personnes par
    logement, historique des quartiers, 1968-2019.
    """
    return await client.get_community_populations(
        community=community,
        start_year=start_year,
        end_year=end_year,
        by=by,
        limit=limit,
        offset=offset,
        lang=lang,
    )
