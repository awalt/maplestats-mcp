"""Constants for the Open Alberta file reader.

Verified live on 2026-10-02 against open.alberta.ca (CKAN):

- 3,018 datasets of type `opendata`; 3,016 are under "Open Government
  Licence - Alberta" (license_id `OGLA`). About 700 have an XLSX resource,
  221 a CSV and 120 an XLS. The DataStore has no active resources
  (`datastore_active` is false on every resource sampled), so the files are
  the only route to the rows.
- Files sit at /dataset/<dataset id>/resource/<resource id>/download/<name>
  on the portal host and download directly (HTTP 200, no redirect). Some
  resources are links to other hosts (for example regionaldashboard.alberta.ca
  exports with no file extension); those are listed but not read.
- Discovery goes through the CKAN Action API, and API calls and file
  downloads share one bucket of one request per 10 seconds.
- The OGL-Alberta text relied on: "worldwide, royalty-free, perpetual,
  non-exclusive licence to use the Information, including for commercial
  purposes", with the attribution statement below.
"""

DOMAIN = "open.alberta.ca"
SITE = f"https://{DOMAIN}"
API_BASE = f"{SITE}/api/3/action/"
DATASET_URL = SITE + "/dataset/{name}"
LICENCE_URL = f"{SITE}/licence"

DOWNLOAD_PATH_PATTERN = (
    r"^/dataset/(?P<dataset>[0-9a-f-]{36})/resource/(?P<resource>[0-9a-f-]{36})/download/[^/]+$"
)
READABLE_SUFFIXES = (".xlsx", ".xls", ".csv")
FORMATS = ("xlsx", "xls", "csv")

OGL_LICENCE_ID = "OGLA"
OGL_ATTRIBUTION = "Contains information licensed under the Open Government Licence – Alberta."

# One request per 10 seconds, API and downloads together. Capacity 1 lets
# the first call go at once.
RATE_LIMIT_SOURCE = "ab-opendata"
RATE_LIMIT_PER_SECOND = 0.1
RATE_LIMIT_CAPACITY = 1.0

CACHE_TTL_API_SECONDS = 6 * 60 * 60
CACHE_TTL_FILE_SECONDS = 6 * 60 * 60
# An unknown dataset name is remembered this long, so asking again does not
# wait 10 seconds for the paced API to say no again.
CACHE_TTL_MISSING_SECONDS = 5 * 60

# Biggest files seen: a 10.4 MB wildfire CSV and 2.3 MB traffic workbooks.
# Only raw bytes are cached; each call scans the file once.
MAX_FILE_BYTES = 40 * 1024 * 1024
NOTES_EXCERPT_CHARS = 300

DATASETS_LIMIT_DEFAULT = 20
DATASETS_LIMIT_MAX = 50
ORGANIZATIONS_FACET_LIMIT = 200
ROWS_LIMIT_DEFAULT = 50
ROWS_LIMIT_MAX = 1000

PROVENANCE_SOURCE = "open-alberta"

# Treasury Board and Finance (Office of Statistics and Information) products with
# named tools. Dataset slugs and file layouts checked live on 2026-11-19:
# - alberta-activity-index-data-tables: one XLSX, sheet "AAX", row 1 is the header
#   ("Alberta Activity Index (January 1981 = 100)" over a blank date column), then
#   one row per month from 1981-01-01 (548 months to August 2026). Updated monthly;
#   the resource keeps its id and the file is replaced.
# - alberta-population-projections-<first year>-2051 (2024, 2025 and 2026 editions
#   follow this slug; 2023's does not): 17 XLSX files, one per geography. The
#   provincial "all assumptions" file has sheets "Low Scenario", "Med Scenario" and
#   "High Scenario"; every sub-provincial file is the medium scenario with one sheet
#   per area (census division codes 4801 to 4819, CMA names). Each sheet has two or
#   three title rows, then Year, Gender (Women +, Men +, All), Total and single
#   years of age 0 to 100 (101 columns), from 2001 (estimates) to 2051, then notes. The summary
#   file has one sheet "Alberta" with population, growth, ratios and components of
#   growth (births, deaths, migration) by year.
ACTIVITY_INDEX_DATASET = "alberta-activity-index-data-tables"
ACTIVITY_INDEX_DEFAULT_MONTHS = 24
PROJECTIONS_DATASET = "alberta-population-projections-{edition}-2051"
PROJECTIONS_LATEST_KNOWN = 2026
PROJECTIONS_FIRST_EDITION = 2024
# Words of each resource's title (lower case) that pick its geography's file.
PROJECTION_GEOGRAPHIES = {
    "alberta": "all assumptions",
    "census_division": "census divisions",
    "census_metropolitan_area": "census metropolitan areas",
    "economic_region": "economic regions",
    "local_geographic_area": "local geographic areas (lgas)",
    "aggregated_local_geographic_area": "aggregated local geographic areas",
    "css_region": "community and social services",
    "land_use_framework_region": "land use framework",
    "health_subzone": "health subzones",
    "health_status_area": "health status areas",
    "health_corridor": "health corridors",
    "health_peer_group": "health peer groups",
    "school_authority_public": "school authorities, public",
    "school_authority_separate": "school authorities, separate",
    "school_authority_francophone": "school authorities, francophone",
}
PROJECTION_SUMMARY = "summary"
PROJECTION_SCENARIO_SHEETS = {"low": "low", "medium": "med", "high": "high"}

# Alberta budget fiscal plan tables (Treasury Board and Finance), checked live on
# 2026-11-24. Two datasets, both OGLA: Budget 2026 onward sits in
# "...-and-tax-plan-2026" ("[2026-2029 to current]", six XLSX: capital plan,
# economic outlook, expense, revenue, tax plan, other tables), and Budgets 2017 to
# 2025 in the older slug without the year (49 XLSX). Resources are named
# "<first year>-<last year> fiscal plan : <part> tables" ("2026-2029 fiscal plan :
# economic outlook tables", "2025-28 fiscal plan : expense tables"); the 2024
# "other tables" resource is typed OTHERS but is an .xlsx. Each workbook opens on a
# picture-only "Cover" sheet; the Economic Outlook workbook holds the Key Energy and
# Economic Assumptions, the chart data (charts 1 to 16), the scenario table and ten
# private-forecaster benchmark sheets (the outlook publication itself is a PDF).
BUDGET_DATASET_CURRENT = "alberta-budget-fiscal-plan-tables-economic-outlook-and-tax-plan-2026"
BUDGET_DATASET_HISTORY = "alberta-budget-fiscal-plan-tables-economic-outlook-and-tax-plan"
BUDGET_FIRST_CURRENT_EDITION = 2026
BUDGET_FIRST_EDITION = 2017
BUDGET_DEFAULT_PART = "economic outlook"
BUDGET_ROWS_MAX = 600
