"""Cue words and tool tables that keep a step out of a plan the question does not need.

A plan listed every source that touched the question's topics or places, and the
model followed them: the Kelowna household-income plan sent it to Borealis tables, the
2001-2016 archive and the census boundary maps, and "rent in Edmonton" to Edmonton
Police, Transit and EPCOR water (chat demo, 2026-11-16). A step stays when the question
uses one of its cue words. Terms are written as the question is normalized (lower case,
no accents), as in topics.py, and a trailing "*" marks a stem.
"""

from __future__ import annotations

POLICE = (
    "police",
    "crime",
    "criminalite",
    "infraction*",
    "occurrence*",
    "offence*",
    "homicide*",
    "assault*",
    "theft*",
    "robbery",
    "shooting*",
    "arrest*",
)
TRANSIT = (
    "transit",
    "bus",
    "train",
    "lrt",
    "alert*",
    "schedule*",
    "timetable",
    "route*",
    "autobus",
    "horaire*",
    "transport en commun",
    "transport collectif",
)
WATER = (
    "water",
    "drinking",
    "epcor",
    "tap",
    "fluoride",
    "chlorine",
    "eau",
    "eau potable",
)
ENERGY = (
    "energy",
    "oil",
    "gas",
    "pipeline*",
    "wells",
    "drilling",
    "petroleum",
    "lng",
    "regulator",
    "energie",
    "petrole",
    "gaz",
    "puits",
    "forage",
)

# A topic step for a source most questions on its topic do not need, by tool name: it
# stays only when the question uses a cue. The cues are the step's own `terms` and
# `patterns` plus the words here, so a step that names its own cues keeps them. The
# older-census tools answer "census 2011", not "household income in Kelowna".
OLDER_CENSUS = (
    "2016",
    "older census",
    "previous census",
    "earlier census",
    "archive*",
    "beyond 20 20",
    "ivt",
    "custom census",
    "custom tabulation",
    "recensement precedent",
    "recensements precedents",
    "recensements anterieurs",
    "recensement historique",
)
BOUNDARIES = (
    "boundary",
    "boundaries",
    "shapefile*",
    "geometry",
    "cartographic",
    "geography file*",
    "polygon*",
    "limite*",
    "carte*",
    "cartographique*",
)
# A tool name or prefix to the words that ask for it, on top of the step's own terms. A step
# with no terms and no words here is never trimmed.
SIDE_TRIPS: dict[str, tuple[str, ...]] = {
    "borealis_search_ivt": OLDER_CENSUS,
    "statcan_census_profile_archive_": OLDER_CENSUS,
    "statcan_geo_list_services": BOUNDARIES,
    # Census geography lookups (codes, UIDs, small areas): the steps name their cue words.
    "statcan_geosuite_": (),
    "rdaas_get_classification_categories_detailed": (),
    # A guide's or reference paper's own text answers a definition or a method question.
    "statcan_reference_": (),
    "boc_search_groups": (),
    # The IMF is a separate publisher: its steps stay out of a plan unless the question names
    # the IMF or the World Economic Outlook (the steps' own terms).
    "imf_": (),
    "boc_get_group_observations": (),
    # An occupation, wage or classification lookup, a Toronto building-score or short-term
    # rental table: each names its cue words as the step's terms.
    "jobbank_": (),
    "rdaas_search_classifications": (),
    "toronto_summarize_": (),
    "toronto_get_neighbourhood_profile": (),
    # Measured on the discovery benchmark: gating these cost no plan metric.
    # A past release of a series, for a question about vintages and revisions, not a Delta File.
    "wds_get_series_as_of": (),
    "boc_search_series": (),
    "cimt_": (),
    "sdmx_space_": (),
}

# A topic step for one province's dashboard, by tool prefix and province: it belongs only
# when the question names that province or one of its cities. Its own purpose says so
# ("Alberta dashboard tables, when the question is Alberta"). client.py's
# _PROVINCE_TOOLS keeps a province's tools for a question that names no place at all;
# these do not.
PROVINCE_ONLY_TOOLS: dict[str, str] = {
    "ab_economic_": "Alberta",
}
