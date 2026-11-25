"""The geospatial tool classes, and the `MAPLE_GIS` switch that hides the pure ones.

One server keeps every tool by default. `MAPLE_GIS=0` runs the same install as a
statistics-only profile: the PURE class below leaves `search_tools`, `plan_query`,
`call_tool`, the server instructions and `docs://catalogue`, and a whole module that is
nothing but PURE tools (bcgw, nrcan_nbac, nrcan_geo) is not registered, so preload does not
import it. Nothing changes while the variable is unset (see docs/ROADMAP.md, "GIS tools").

PURE: geometry, a layer, a grid or a boundary file, or geocoding is the product.
HYBRID: rows or figures served from a GIS endpoint (ArcGIS REST, WFS, OGC API) or carrying
coordinates; the answer a statistics user wants is tabular. HYBRID tools are never hidden:
the class is recorded here for the documentation and the tests, so a tool added later has
one obvious place to be classified. Six PURE tools are borderline (marked `*`): their
default answer is attributes or a time series, but the source is a polygon composite, a
grid or a geocoder.

The class lists were derived from tool_catalogue.json and the module code on 2026-11-17
(14 PURE and 40 HYBRID of 463 tools); tests/test_gis_profile.py keeps every name real.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from maplestats_mcp import config

PURE_GIS_TOOLS: frozenset[str] = frozenset(
    {
        # bcgw: OGC WFS 2.0 on BC's geospatial warehouse; any layer by type_name.
        "bcgw_get_active_wildfires",
        "bcgw_get_mining_tenure",
        "bcgw_query_layer",
        # statcan_geo: census boundary MapServers (point in polygon, bbox, polygons).
        "statcan_geo_get_layer_detail",
        "statcan_geo_list_services",
        "statcan_geo_query_layer",
        # eccc_coverages (*): OGC API Coverages grids (CMIP6, CMIP5).
        "eccc_coverages_describe",
        "eccc_coverages_get_data",
        "eccc_coverages_search",
        # nrcan_nbac (*): burned-area polygon composite through WFS.
        "nrcan_nbac_query_fires",
        # nrcan_geo (*): geolocator and gazetteer.
        "nrcan_geo_locate",
        "nrcan_geo_search_names",
        # Fire perimeters are polygons; the other tools of both modules are HYBRID.
        "ab_wildfire_get_fire_perimeters",
        "cwfis_get_fire_perimeters",
    }
)

HYBRID_GIS_TOOLS: frozenset[str] = frozenset(
    {
        # statcan_geo spatial layers: deprivation index, housing need, road network.
        "statcan_geo_get_spatial_layer_detail",
        "statcan_geo_list_spatial_layers",
        "statcan_geo_query_spatial_layer",
        # eccc GeoMet items: alerts, observations, AQHI, hydrometric.
        "eccc_get_collection",
        "eccc_list_collections",
        "eccc_query_items",
        "eccc_search_collections",
        # ab_wildfire: fire points, danger lookup, bans, municipal fires, statistics.
        "ab_wildfire_get_fire_danger",
        "ab_wildfire_get_fire_restrictions",
        "ab_wildfire_get_fires",
        "ab_wildfire_get_municipal_fires",
        "ab_wildfire_get_season_statistics",
        "ab_wildfire_summarize_fire_danger",
        "ab_wildfire_summarize_fires",
        # cwfis: hotspots, stations, forecasts, situation reports, large fires.
        "cwfis_get_fire_danger",
        "cwfis_get_fire_weather_forecast",
        "cwfis_get_hotspots",
        "cwfis_get_situation_report",
        "cwfis_get_weather_stations",
        "cwfis_list_situation_reports",
        "cwfis_search_large_fires",
        # arcgis_hub: a portal family like CKAN and Socrata; permits, licences, inspections.
        "arcgis_hub_get_dataset",
        "arcgis_hub_list_portals",
        "arcgis_hub_query_feature_layer",
        "arcgis_hub_query_file",
        "arcgis_hub_search_datasets",
        # Tabular records on ArcGIS REST and Open511.
        "eps_get_last_load_date",
        "eps_list_occurrences",
        "eps_summarize_occurrences",
        "ised_spectrum_query_licences",
        "drivebc_get_event",
        "drivebc_list_areas",
        "drivebc_search_events",
        "drivebc_summarize_events",
        "earthquakes_search",
        # statcan_lode: facility, address and building databases with coordinates.
        "statcan_lode_describe",
        "statcan_lode_list_databases",
        "statcan_lode_list_files",
        "statcan_lode_list_zip",
        "statcan_lode_preview_member",
        "statcan_lode_query",
    }
)


def hidden_tools() -> frozenset[str]:
    """The tools the profile hides right now: the PURE class under MAPLE_GIS=0, else none."""
    return frozenset() if config.get_gis_enabled() else PURE_GIS_TOOLS


# Text that names a hidden tool ----------------------------------------------------------
#
# The tools leave the catalogue, but the prose around them is hand-written: the routing
# index sent to every client, the module descriptions behind docs://catalogue, and two
# other tools' listings that point at a PURE tool. Each is cut here, by the exact words, and
# only while MAPLE_GIS is off. The default text is never touched, so it stays byte for byte
# what it was. tests/test_gis_profile.py fails, naming the cut, when an edit to the source
# text stops one of these from matching.


@dataclass(frozen=True)
class Cut:
    """Remove `start` through `end` (both included) from a text; `start` alone when no `end`."""

    start: str
    end: str | None = None

    def apply(self, text: str) -> str:
        first = text.find(self.start)
        if first < 0:
            return text
        last = first + len(self.start)
        if self.end is not None:
            stop = text.find(self.end, last)
            if stop < 0:
                return text
            last = stop + len(self.end)
        return text[:first] + text[last:]


def cut_text(text: str, cuts: Iterable[Cut]) -> str:
    """`text` with every cut applied, or untouched while the PURE class is switched on."""
    if config.get_gis_enabled():
        return text
    for cut in cuts:
        text = cut.apply(text)
    return text


# server.SERVER_INSTRUCTIONS: the prefixes of the three wholly PURE modules and of the
# coverages. `statcan_geo_`, `cwfis_` and `ab_wildfire_` stay named: HYBRID tools use them.
INSTRUCTION_CUTS: tuple[Cut, ...] = (
    Cut("\n  gridded climate projections (CMIP6/CMIP5, SSP/RCP): eccc_coverages_;"),
    Cut("nrcan_geo_ (geocoding, place names), "),
    Cut("nrcan_nbac_\n  (burned areas), "),
    Cut("bcgw_ (BC Geographic\n  Warehouse), "),
    # The census-boundary tools are PURE; the spatial layers after them are HYBRID.
    Cut("census boundaries; "),
)

# Module descriptions (docs://catalogue), by module folder and language. A module that is
# only PURE tools is left out of the page whole (catalogue.module_hidden).
DESCRIPTION_CUTS: dict[tuple[str, str], tuple[Cut, ...]] = {
    ("eccc", "en"): (Cut(" The eccc_coverages_ tools read", "for a point or area."),),
    ("eccc", "fr"): (Cut(" Les outils eccc_coverages_ lisent", "pour un point ou une zone."),),
    ("ab_wildfire", "en"): (Cut("mapped fire perimeters, "),),
    ("ab_wildfire", "fr"): (Cut("périmètres cartographiés, "),),
    ("cwfis", "en"): (Cut("current-season estimated fire perimeters, "),),
    ("cwfis", "fr"): (Cut("périmètres estimés de la saison en cours, "),),
    ("statcan", "en"): (
        Cut(
            "StatCan's census-geography ArcGIS REST service",
            "(the latter by the existing shared retry layer). ",
        ),
    ),
    ("statcan", "fr"): (
        Cut(
            "Le service de géographie du recensement ArcGIS REST",
            "(la seconde par la couche de nouvelles tentatives déjà partagée). ",
        ),
    ),
}

# Two tools outside the class whose listing sends the reader to one that is hidden.
TOOL_DESCRIPTION_CUTS: dict[str, tuple[Cut, ...]] = {
    "earthquakes_search": (Cut(" Use nrcan_geo_locate to turn a\nplace into coordinates."),),
    "eccc_list_collections": (
        Cut(",\nwhich are gridded coverages read with eccc_coverages_get_data"),
    ),
}

# The two pages of the eccc module that send the reader to the coverages tools.
RESOURCE_CUTS: dict[str, tuple[Cut, ...]] = {
    "docs://eccc/well-known-collections": (
        Cut(" The `climate:*`\ncollections are gridded coverages", "not eccc_query_items."),
    ),
    "docs://eccc/fr/collections-courantes": (
        Cut(
            " Les collections\n`climate:*` sont des couvertures maillées",
            "pas avec eccc_query_items.",
        ),
    ),
}


# The planner's wording -----------------------------------------------------------------

_NAMES = "|".join(sorted(map(re.escape, PURE_GIS_TOOLS), key=len, reverse=True))
_MENTION = re.compile(rf"(?<![a-z0-9_])(?:{_NAMES})(?![a-z0-9_])")
# "(from nrcan_geo_locate)" and its French "(tirées de nrcan_geo_locate)".
_POINTER = re.compile(rf"\s*\([^()]*(?<![a-z0-9_])(?:{_NAMES})(?![a-z0-9_])[^()]*\)")


def names_hidden_tool(text: str) -> bool:
    """Whether `text` names a PURE tool, and the profile has hidden it."""
    return not config.get_gis_enabled() and _MENTION.search(text) is not None


def without_pointers(text: str) -> str:
    """`text` less any parenthesis that points at a hidden tool; unchanged while shown."""
    if config.get_gis_enabled():
        return text
    return _POINTER.sub("", text)
