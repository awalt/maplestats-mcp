"""Constants for the 2021 Census Profile SDMX API.

Confirmed live 2026-09-20 against
`https://api.statcan.gc.ca/census-recensement/profile/sdmx/rest/` — a
different host and a genuinely different SDMX implementation than
`modules/statcan/sdmx` (www150.statcan.gc.ca, XML-only, generic
table/vector data). This one is documented at
https://www12.statcan.gc.ca/wds-sdw/2021profile-profil2021-eng.cfm and
actually honours `format=jsondata`, returning self-describing SDMX-JSON
(dimension labels embedded alongside the data, so a caller does not
need a separate metadata call to read a response). No API key or
session is required.

Geography is split across 14 dataflows, one per geography level, each
with its own geography codelist sharing the DATAFLOW_ID's suffix
(`DF_CD` <-> `CL_GEO_CD`, etc.) — confirmed live for every level below.
`CL_CHARACTERISTIC` (2,631 codes), `CL_GENDER` (3 codes), and
`CL_STATISTIC` (2 codes) are shared across all geography levels.
"""

BASE_URL = "https://api.statcan.gc.ca/census-recensement/profile/sdmx/rest"
AGENCY = "STC_CP"

RATE_LIMIT_SOURCE = "statcan-census-profile"
RATE_LIMIT_PER_SECOND = 5.0
RATE_LIMIT_CAPACITY = 10.0

CACHE_TTL_CODELIST_SECONDS = 24 * 60 * 60
# A codelist usually answers in 0.5 to 1.9 s, but slow outliers reach the old 30 s
# default: 23.5 s (warm-up, client.warm_codelists) and 27.7 s (a plain curl of
# CL_GEO_PR, 2026-11-19). 45 s leaves room for them. Not 60 like `get_data`: a timeout
# is retried (shared/http.py, 3 attempts), and two 45 s attempts still end inside the
# 120 s tool timeout (MAPLE_TOOL_TIMEOUT_SECONDS), so the caller gets this module's
# "did not respond in time" error rather than the server's generic one.
CODELIST_TIMEOUT_SECONDS = 45.0
# One `data` request takes 33 to 47 s (client.py, note 3), so each attempt waits 60 s.
# shared/http.py retries a timeout up to 3 times, 180 s and more in all, past the 120 s
# default tool timeout (MAPLE_TOOL_TIMEOUT_SECONDS; the hosted server sets 230 s). The
# attempts together are cut at data_budget_seconds(), leaving 30 s of the tool's time,
# as bcer and wds/query.py do, so the caller gets this module's error naming the
# census API's slowness rather than the server's generic timeout.
DATA_TIMEOUT_SECONDS = 60.0


def data_budget_seconds() -> float:
    """Seconds every attempt at one `data` request may take together: never less than
    one full attempt, else what the tool timeout leaves after 30 s."""
    from maplestats_mcp import config

    return max(DATA_TIMEOUT_SECONDS, config.get_tool_timeout_seconds() - 30.0)


# The raw response of one request, kept in shared/cache.py's memory cache (its own
# entry and megabyte caps apply). It mainly lets requests for the same missing values
# share one 35 s upstream call; the long-lived copy is the per-value store below.
CACHE_TTL_DATA_SECONDS = 60 * 60

# The per-value store (value_store.py): each value on its own, in memory and in one file.
# Lifetime: the 2021 Census Profile is a fixed release (re-issued only for corrections,
# last on 2022-09-21), so values are kept 14 days: long enough that a repeat or an
# overlapping question across restarts and quiet weeks is instant, short enough that a
# correction reaches the server within two weeks.
VALUE_TTL_SECONDS = 14 * 24 * 60 * 60
# Size: at most 8 MB of record text (a value is 200 to 400 bytes, measured 2026-11-17: 205
# for six income and population values, so 20,000 to 40,000 values), in memory and in the
# file alike, so about 10 to 16 MB resident and at most 8 MB on disk.
# The least recently used values go first. The file sits beside the siblings' caches
# (config.get_census_cache_dir(); /data/census on the hosted server).
VALUE_STORE_MAX_BYTES = 8 * 1024 * 1024
VALUE_STORE_FILE = "census_profile_values.jsonl"
# Bump to make a server ignore (and move aside) a file written by another layout.
VALUE_STORE_VERSION = 1

# Codelists warmed in the background when the hosted server starts: the four the first
# questions use (characteristics, provinces, census divisions, metro areas and agglomerations).
WARM_CODELISTS = ("CL_CHARACTERISTIC", "CL_GEO_PR", "CL_GEO_CD", "CL_GEO_CMACA")

GEOGRAPHY_SEARCH_LIMIT_DEFAULT = 20
GEOGRAPHY_SEARCH_LIMIT_MAX = 200
CHARACTERISTIC_SEARCH_LIMIT_DEFAULT = 20
CHARACTERISTIC_SEARCH_LIMIT_MAX = 200

CHARACTERISTIC_CODELIST = "CL_CHARACTERISTIC"

# level -> (dataflow id, geography codelist id)
GEOGRAPHY_LEVEL_TO_DATAFLOW = {
    "canada_provinces_territories": ("DF_PR", "CL_GEO_PR"),
    "census_divisions": ("DF_CD", "CL_GEO_CD"),
    "census_subdivisions": ("DF_CSD", "CL_GEO_CSD"),
    "dissolved_census_subdivisions": ("DF_DCSD", "CL_GEO_DCSD"),
    "census_metro_areas": ("DF_CMACA", "CL_GEO_CMACA"),
    "census_tracts": ("DF_CT", "CL_GEO_CT"),
    "dissemination_areas": ("DF_DA", "CL_GEO_DA"),
    "aggregate_dissemination_areas": ("DF_ADA", "CL_GEO_ADA"),
    "designated_places": ("DF_DPL", "CL_GEO_DPL"),
    "economic_regions": ("DF_ER", "CL_GEO_ER"),
    "federal_electoral_districts": ("DF_FED", "CL_GEO_FED"),
    "forward_sortation_areas": ("DF_FSA", "CL_GEO_FSA"),
    "health_regions": ("DF_HR", "CL_GEO_HR"),
    "population_centres": ("DF_POPCNTR", "CL_GEO_POPCNTR"),
}

# A DGUID starts with the vintage year, "A" (administrative) or "S" (statistical) and a
# four-digit geography type: 9 characters that name the level. Read from the 14 live
# geography codelists on 2026-11-17 (80,278 codes): every code of a codelist has one of
# that level's prefixes and no prefix occurs in two levels. Canada (2021A0000) sits
# in the province list; the 2016-vintage dissolved subdivisions (2016A0005) and the 2023
# federal electoral districts (2023A0004) and 2022 health regions (2022A0007/8) keep
# their own vintage, so a prefix without a level here is a new vintage, never guessed.
DGUID_PREFIX_TO_LEVEL = {
    "2021A0000": "canada_provinces_territories",
    "2021A0002": "canada_provinces_territories",
    "2021A0003": "census_divisions",
    "2021A0005": "census_subdivisions",
    "2016A0005": "dissolved_census_subdivisions",
    "2021S0503": "census_metro_areas",
    "2021S0504": "census_metro_areas",
    "2021S0505": "census_metro_areas",
    "2021S0506": "census_metro_areas",
    "2021S0507": "census_tracts",
    "2021S0512": "dissemination_areas",
    "2021S0516": "aggregate_dissemination_areas",
    "2021A0006": "designated_places",
    "2021S0500": "economic_regions",
    "2023A0004": "federal_electoral_districts",
    "2021A0011": "forward_sortation_areas",
    "2022A0007": "health_regions",
    "2022A0008": "health_regions",
    "2021S0510": "population_centres",
}

# Confirmed live via CL_GENDER/CL_STATISTIC codelists.
GENDER_TO_CODE = {"total": "1", "men": "2", "women": "3"}
STATISTIC_TO_CODE = {"counts": "1", "rate": "4"}
