"""MCP tools for the BC Energy Regulator's bulk well, production and facility files."""

from __future__ import annotations

from typing import Literal

from fastmcp.tools import tool

from maplestats_mcp.modules.bcer import client, constants
from maplestats_mcp.modules.bcer.schemas import (
    BcerFileList,
    BcerProduction,
    BcerRecords,
    BcerWellList,
)

Lang = Literal["en", "fr"]


@tool
async def bcer_list_files(include_members: bool = False, lang: Lang = "en") -> BcerFileList:
    """List the BC Energy Regulator (BCER) bulk files this module reads: each file's
    size, last-modified date, layout notes and which tool reads it, plus what BCER
    states about reuse.

    The files sit in BCER's legacy IRIS download area (Legacy Well Lookup & Data
    Downloads): well index, monthly production by well zone, drilling and completion
    tables, hydraulic fracture and perforation records, directional surveys, facility
    index and gas plant capacities. include_members=true also lists the members of each
    zip (compressed and inflated sizes) and, for the drilling and fracture zips, BCER's
    own record counts and 'History to' date from the readme. Fixed-width text copies and
    the well index PDFs are listed but not read.
    Terms: BCER states no licence for these files, and its website terms ask for written
    permission before material is reproduced or redistributed. Use the data for personal
    or internal analysis and check with BCER before reuse beyond that.
    Use for: knowing how fresh BCER's well and production files are, what each holds
    and where to download the whole file yourself.
    Keywords: BCER, BC Energy Regulator, British Columbia, BC Oil and Gas Commission,
    IRIS, well index, production data, drilling data, data downloads, file list, oil and
    gas data, bulk files.
    Mots-clés : BCER, BC Energy Regulator, Colombie-Britannique, Commission du pétrole et
    du gaz de la C.-B., IRIS, index des puits, données de production, données de forage,
    téléchargement de données, liste des fichiers, pétrole et gaz, fichiers massifs.
    """
    return await client.list_files(include_members=include_members, lang=lang)


@tool
async def bcer_search_wells(
    well_authorization: str | None = None,
    uwi: str | None = None,
    name: str | None = None,
    location: str | None = None,
    operator: str | None = None,
    status: str | None = None,
    fluid: str | None = None,
    area_code: str | None = None,
    formation_code: str | None = None,
    well_class: str | None = None,
    rig_release_from: str | None = None,
    rig_release_to: str | None = None,
    limit: int = constants.WELLS_DEFAULT,
    offset: int = 0,
    lang: Lang = "en",
) -> BcerWellList:
    """Search the BC Energy Regulator (BCER) well index of British Columbia: about
    40,000 oil, gas, water and other wells (about 49,000 rows, one per pool or completion), by well
    authorization number, UWI, name, location, operator, status, fluid, area, formation,
    class or rig-release date, with each well's operator and surface coordinates.

    well_authorization takes one or several numbers ("1811", "01811, 01812"); uwi is the
    16-character identifier or its start; name and location match text anywhere
    (spacing ignored); operator is a client id or part of a company name ("Tourmaline",
    "Canbriam"; ids and names: bcer_get_reference_table, table='operators'); status
    and fluid take BCER codes, comma-separated (status ACT, ABAN, CANC, SUSP, WAG, COMP,
    DRIL; fluid GAS, OIL, WATR, MGAS, MOIL, UND); area_code and formation_code are
    BCER codes (formation 5000 is Montney; look codes up with bcer_get_reference_table,
    table='codes' or 'areas'); well_class is DV, EW, EO, EX...; rig_release_from/to take
    '2024', '2024-03' or '2024-03-15'. Rows come back in well-number order; page with
    offset. The file is rebuilt daily and held for an hour.
    Terms: BCER states no licence for this file, and its website terms ask for written
    permission before material is reproduced or redistributed. Use the data for personal
    or internal analysis and check with BCER before reuse beyond that.
    Use for: finding a British Columbia well's authorization number, UWI, status,
    operator or location before asking for its production or drilling records, and
    counting wells by status, fluid, area or operator.
    Keywords: BCER, BC Energy Regulator, British Columbia, well index, well
    authorization number, WA number, UWI, wells, operator, well status, abandoned wells,
    Montney, northeast BC, oil and gas wells, well search.
    Mots-clés : BCER, BC Energy Regulator, Colombie-Britannique, index des puits, numéro
    d'autorisation de puits, UWI, puits, exploitant, statut du puits, puits abandonnés,
    Montney, nord-est de la C.-B., puits de pétrole et de gaz, recherche de puits.
    """
    return await client.search_wells(
        well_authorization=well_authorization,
        uwi=uwi,
        name=name,
        location=location,
        operator=operator,
        status=status,
        fluid=fluid,
        area_code=area_code,
        formation_code=formation_code,
        well_class=well_class,
        rig_release_from=rig_release_from,
        rig_release_to=rig_release_to,
        limit=limit,
        offset=offset,
        lang=lang,
    )


@tool
async def bcer_get_production(
    well_authorization: str | None = None,
    uwi: str | None = None,
    operator: str | None = None,
    area_code: str | None = None,
    formation_code: str | None = None,
    from_period: str | None = None,
    to_period: str | None = None,
    limit: int = constants.PRODUCTION_ROWS_DEFAULT,
    lang: Lang = "en",
) -> BcerProduction:
    """Monthly oil, gas, water and condensate production in British Columbia from the
    BC Energy Regulator (BCER) production files (1954 to the latest published month), for
    a well, a list of wells, an operator, an area or formation, or the whole province,
    with monthly totals and the most recent well-zone rows.

    Select with well_authorization (one or several numbers), uwi, operator (client id or
    part of a company name), area_code and formation_code (BCER codes; Montney is
    formation 5000), or none of them for province-wide totals, which then need
    from_period. from_period and to_period take a year or month ('2024', '2024-03'):
    only the period files that overlap are read, so a recent range is fast (the
    2025-to-present file is 3.7 MB) and a whole history is slow; for named wells with
    no period, files before the well index's first-production period are skipped. The
    124 MB archive is read by range requests and filtered as it streams, never
    downloaded: one call reads at most 64 MB compressed and 60 seconds, and when that
    ends a read early, `complete` is false and provenance.limits say how far it got.
    monthly_totals sum every matching well zone per month (gas in e3m3, oil, water and
    condensate in m3, wells reporting); records are the latest `limit` well-zone-month
    rows with cumulatives.
    Terms: BCER states no licence for these files, and its website terms ask for written
    permission before material is reproduced or redistributed. Use the data for personal
    or internal analysis and check with BCER before reuse beyond that.
    Use for: how much gas or oil a British Columbia well, an operator's wells or the
    Montney produced each month, and BC's monthly gas, oil and water totals.
    Keywords: BCER, BC Energy Regulator, British Columbia, production, monthly production,
    gas production, oil production, natural gas, Montney, well production, operator
    production, condensate, water production, BC gas.
    Mots-clés : BCER, BC Energy Regulator, Colombie-Britannique, production, production
    mensuelle, production de gaz, production de pétrole, gaz naturel, Montney, production
    d'un puits, production d'un exploitant, condensat, production d'eau, gaz de la C.-B.
    """
    return await client.get_production(
        well_authorization=well_authorization,
        uwi=uwi,
        operator=operator,
        area_code=area_code,
        formation_code=formation_code,
        from_period=from_period,
        to_period=to_period,
        limit=limit,
        lang=lang,
    )


@tool
async def bcer_get_drilling_records(
    well_authorization: str,
    table: str = "drill_ev",
    limit: int = constants.ROWS_DEFAULT,
    lang: Lang = "en",
) -> BcerRecords:
    """Drilling, completion, test and status records of one British Columbia well from
    the BC Energy Regulator (BCER) drilling tables (drill_csv.zip), as published.

    well_authorization is one number ("01811"; find it with bcer_search_wells). table
    picks the record type: drill_ev (drilling events: depths, spud and rig-release dates),
    wells (header: name, surface location, operator), w_status and c_status (status
    history), compl_ev and compl_wo (completions, stimulation, flow tests), casings,
    form_top (formation tops), aban_dtl and aban_frm (abandonment plugs), aofp_tst,
    aofp_dtl, dst, dst_rate, pst, pst_dtl (flow and pressure tests), core_cut, logs_run,
    pay_zone, gas_anal, oil_anal, wtr_anal (cores, logs, analyses), gas_inj, wtr_inj,
    water_gas_disposal (monthly injection and disposal). Columns and codes are BCER's
    (decode with bcer_get_reference_table). The member is read by range requests
    (0.1 to 11 MB compressed) and stops at the well's last row; the zip is not
    downloaded.
    Terms: BCER states no licence for these files, and its website terms ask for written
    permission before material is reproduced or redistributed. Use the data for personal
    or internal analysis and check with BCER before reuse beyond that.
    Use for: a British Columbia well's casing program, formation tops, completion and
    abandonment history, drill stem and pressure tests, or status changes.
    Keywords: BCER, BC Energy Regulator, British Columbia, drilling records, well
    completion, casing, formation tops, abandonment, drill stem test, well status
    history, workover, well file, wells.
    Mots-clés : BCER, BC Energy Regulator, Colombie-Britannique, dossiers de forage,
    complétion de puits, tubage, sommets de formations, abandon, essai aux tiges,
    historique de statut, reconditionnement, dossier de puits, puits.
    """
    return await client.get_drilling_records(
        well_authorization=well_authorization, table=table, limit=limit, lang=lang
    )


@tool
async def bcer_get_fracture_records(
    well_authorization: str,
    table: str = "hydraulic_fracture",
    limit: int = constants.ROWS_DEFAULT,
    lang: Lang = "en",
) -> BcerRecords:
    """Hydraulic fracture, perforation and perforation-interval records of one British
    Columbia well from the BC Energy Regulator (BCER) hydraulic fracture files, as
    published.

    well_authorization is one number ("02777"). table is hydraulic_fracture (one row per
    frac stage: base fluid, fluids and CO2 or N2 pumped, proppant types and tonnes,
    breakdown, treating and shut-in pressures, rate, gradient), perf (perforation charge
    type, size, shots per metre, phasing) or perf_net_interval (top and base depth of each
    perforated interval). BCER's chemical disclosure (FracFocus) is not in these files.
    The member is read by range requests (1.7 to 7.7 MB compressed) and stops at the
    well's last row.
    Terms: BCER states no licence for these files, and its website terms ask for written
    permission before material is reproduced or redistributed. Use the data for personal
    or internal analysis and check with BCER before reuse beyond that.
    Use for: how a British Columbia well was fracked: number of stages, fluid volume,
    proppant, pressures and perforation intervals.
    Keywords: BCER, BC Energy Regulator, British Columbia, hydraulic fracturing, fracking,
    frac stages, proppant, perforations, fluid pumped, treating pressure, completion,
    Montney, horizontal wells.
    Mots-clés : BCER, BC Energy Regulator, Colombie-Britannique, fracturation hydraulique,
    étapes de fracturation, agent de soutènement, perforations, fluide pompé, pression de
    traitement, complétion, Montney, puits horizontaux.
    """
    return await client.get_fracture_records(
        well_authorization=well_authorization, table=table, limit=limit, lang=lang
    )


@tool
async def bcer_get_directional_survey(
    well_authorization: str,
    limit: int = constants.ROWS_DEFAULT,
    lang: Lang = "en",
) -> BcerRecords:
    """Directional survey of one British Columbia well from the BC Energy Regulator
    (BCER): the stations of its wellbore path (measured depth, inclination, azimuth, true
    vertical depth, north-south and east-west offsets), as published.

    well_authorization is one number ("59263"). A survey has tens to thousands of
    stations in depth order; limit (at most 1,000) caps the rows returned and
    rows_matched says how many there are. The 39 MB member (about 2 million stations
    for the province) is read by range requests and stops at the well's last row.
    Terms: BCER states no licence for this file, and its website terms ask for written
    permission before material is reproduced or redistributed. Use the data for personal
    or internal analysis and check with BCER before reuse beyond that.
    Use for: the path of a horizontal or deviated well in British Columbia: its true
    vertical depth, lateral length and offsets.
    Keywords: BCER, BC Energy Regulator, British Columbia, directional survey, wellbore
    path, inclination, azimuth, true vertical depth, TVD, horizontal well, measured
    depth, deviation survey.
    Mots-clés : BCER, BC Energy Regulator, Colombie-Britannique, levé directionnel,
    trajectoire du puits, inclinaison, azimut, profondeur verticale vraie, puits
    horizontal, profondeur mesurée, levé de déviation, trajectoire.
    """
    return await client.get_directional_survey(
        well_authorization=well_authorization, limit=limit, lang=lang
    )


@tool
async def bcer_search_facilities(
    kind: str = "index",
    query: str | None = None,
    operator: str | None = None,
    facility_type: str | None = None,
    status: str | None = None,
    limit: int = constants.ROWS_DEFAULT,
    lang: Lang = "en",
) -> BcerRecords:
    """Search the BC Energy Regulator (BCER) facility files for British Columbia: the
    facility index (batteries, gas plants, compressor stations: code, name, type,
    operator, location, class, compressor power, status and dates) or gas processing
    plant capacities (raw gas, sales gas, propane, butane, pentanes, sulphur).

    kind='index' (default) searches facindex.csv; kind='capacity' searches
    facility_capacity.csv. query matches text in any column (name, code, location);
    operator matches an operator name or code; facility_type ("Gas Processing Plant",
    "Battery Site", "Compressor Station", "Disposal Station"...) and status ("Active",
    "Cancelled", "Removed", "Suspended"...) apply to the index only. The
    files are small, rebuilt daily and kept for an hour; file_date is the file's own print
    or extract date.
    Terms: BCER states no licence for these files, and its website terms ask for written
    permission before material is reproduced or redistributed. Use the data for personal
    or internal analysis and check with BCER before reuse beyond that.
    Use for: finding a British Columbia gas plant, battery or compressor station and its
    operator, or a plant's processing capacity.
    Keywords: BCER, BC Energy Regulator, British Columbia, facilities, gas plants,
    processing capacity, batteries, compressor stations, facility index, sour gas,
    sulphur recovery, natural gas processing.
    Mots-clés : BCER, BC Energy Regulator, Colombie-Britannique, installations, usines de
    gaz, capacité de traitement, batteries, stations de compression, index des
    installations, gaz sulfureux, récupération du soufre, traitement du gaz naturel.
    """
    return await client.search_facilities(
        kind=kind,
        query=query,
        operator=operator,
        facility_type=facility_type,
        status=status,
        limit=limit,
        lang=lang,
    )


@tool
async def bcer_get_reference_table(
    table: str,
    query: str | None = None,
    limit: int = constants.ROWS_DEFAULT,
    lang: Lang = "en",
) -> BcerRecords:
    """Look up the code tables behind BC Energy Regulator (BCER) well data: operator
    (client) ids and names, area (field) codes, formation and status codes, pools,
    projects and facility types, from the drilling zip.

    table is operators (Client Id, name, abbreviation: the ids in a well's operator_id),
    areas (area codes: Area_code in production and the well index), codes (Table ID
    FORT lists formations such as 5000 MONTNEY and 4100 BALDONNEL; WMOD well mode, WFLU
    well fluid, CMOD and CFLU completion mode and fluid, OPNT operation type, and more),
    pools, projects (unit and scheme codes and names), facility_types or
    plant_jurisdictions. query matches text in any column ("montney", "tourmaline",
    "WMOD"). The table is a few KB to 322 KB, read by range request and kept for an hour.
    Terms: BCER states no licence for these files, and its website terms ask for written
    permission before material is reproduced or redistributed. Use the data for personal
    or internal analysis and check with BCER before reuse beyond that.
    Use for: turning a BCER formation, area, status or operator code into a name, or
    finding the code for Montney, an operator or an oil and gas field.
    Keywords: BCER, BC Energy Regulator, British Columbia, formation codes, area codes,
    operator list, well status codes, code tables, Montney formation code, oil and gas
    fields, pools, projects.
    Mots-clés : BCER, BC Energy Regulator, Colombie-Britannique, codes de formation, codes
    de secteur, liste des exploitants, codes de statut des puits, tables de codes, code de
    la formation Montney, champs pétroliers et gaziers, réservoirs, projets.
    """
    return await client.get_reference_table(table=table, query=query, limit=limit, lang=lang)
