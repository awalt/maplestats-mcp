"""Constants for the Ontario Ministry of Finance population projections module.

Checked live on 2026-11-24 against data.ontario.ca (CKAN, portal "on"):

- Dataset `population-projections` (organization `finance`, licence
  OGL-ON-1.0, update frequency yearly) holds 16 XLSX resources: each table in
  English and French under the same resource name, the English files named
  `..._mof_population_projections_...` and the French ones
  `..._projections_demographiques_du_mdf_...` (the resources' `language` field
  is the string "english" or "french"). The annual release (Summer 2026, base
  year 2025) has Ontario, 6 regions, 49 census divisions, 34 public health units,
  9 MCCSS service delivery regions and the components of change; the Fall 2026
  interim update ("Interim ..." resources, base year 2026) has Ontario and its
  components only.
- Every workbook has one sheet: a title row, a "Sources: ..." row naming the
  release in parentheses, a blank row, an age-group band row (BROAD AGE GROUPS,
  5-YEAR AGE GROUPS, SINGLE-YEAR OF AGE), the header row (SCENARIO for the
  Ontario files; YEAR (JULY 1); REGION CODE except the MCCSS file; REGION NAME;
  GENDER; TOTAL; age columns), a blank row, then one row per area, year and
  gender. Genders are MEN+, WOMEN+ and TOTAL ALL GENDERS (TOTAL BOTH GENDERS in
  the census division file); scenarios REFERENCE, LOW-GROWTH, HIGH-GROWTH. The
  public health unit file adds Mean Age and Median Age. Census division names
  carry trailing spaces. The components file has SCENARIO, PERIOD ("2025-26")
  and the components, ending each scenario with a 2051 start-population row.
- Ontario Fact Sheet and Ontario Economic Accounts: HTML pages on ontario.ca under
  Crown copyright (ontario.ca/page/copyright-information): reproduction for
  non-commercial purposes, with credit, unchanged. Layout below (PAGES).
"""

# The ministry's web pages read as published (checked live on 2026-11-24): the
# Fact Sheet (11 HTML tables, no captions on the first, rows as <th scope="row">
# label and <td> value; April 2026 edition) and the Ontario Economic Accounts (7
# tables: 1.1 to 1.6 with a header row in <thead>, then Appendix A release dates;
# Q2 2026 edition, updated October 09, 2026). Both have a French page with the same
# tables, numbers written the French way ("39,0", "1 246 721") and negatives in
# parentheses as in English ("(0,3)"). robots.txt asks for one second between
# requests (Crawl-delay: 1).
PAGES = {
    "fact_sheet": (
        "https://www.ontario.ca/page/ontarios-population-labour-market-economy-and-trade-fact-sheet",
        "https://www.ontario.ca/fr/page/profil-population-marche-travail-economie-echanges-commerciaux-ontario",
    ),
    "economic_accounts": (
        "https://www.ontario.ca/page/ontario-economic-accounts",
        "https://www.ontario.ca/fr/page/comptes-economiques-de-lontario",
    ),
}
PAGES_DOMAIN = "www.ontario.ca"
PAGES_RATE_SOURCE = "ontario-ca"
PAGES_RATE_PER_SECOND = 1.0
CACHE_TTL_PAGE_SECONDS = 6 * 60 * 60
MAX_PAGE_BYTES = 5 * 1024 * 1024
PAGES_PROVENANCE_SOURCE = "on-finance-pages"

PORTAL = "on"
DATASET = "population-projections"
DOMAIN = "data.ontario.ca"
DATASET_URL = "https://data.ontario.ca/dataset/population-projections"

# English files only: the same tables in French carry French headers.
ENGLISH_FILE_MARKER = "mof_population_projections"

# Words of the resource name (lower case) that pick each geography's file.
GEOGRAPHY_FILES = {
    "ontario": "ontario mof population projections",
    "region": "6 regions",
    "census_division": "census divisions",
    "public_health_unit": "public health units",
    "mccss_region": "mccss",
}
COMPONENTS_FILE = "components of provincial demographic change"
INTERIM_PREFIX = "interim"

# The CKAN family's per-portal download bucket for data.ontario.ca (one file
# request a second), shared so this module and ckan_read_resource pace together.
FILES_BUCKET = "ckan-files-on"
FILES_RATE_PER_SECOND = 1.0
MAX_FILE_BYTES = 40 * 1024 * 1024
CACHE_TTL_FILE_SECONDS = 2 * 60 * 60

HEADER_SEARCH_ROWS = 15
ROWS_MAX = 3000

PROVENANCE_SOURCE = "on-finance"
