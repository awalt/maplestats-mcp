"""Constants for CIHI's health workforce data tables (anonymous XLSX workbooks).

Confirmed live 2026-11-16:
- https://www.cihi.ca/en/topics/health-workforce/data-tables lists 45 items,
  10 per page (?page=0 to 4, sorted by date published), each an `article`
  card with the title, a `time datetime` publication date, a one-sentence
  description and a link to a workbook on www.cihi.ca/sites/default/files/
  document/. 43 are `.xlsx`, 2 are `.zip` archives of older releases. The
  French page (/fr/sujets/main-doeuvre-de-la-sante/tableaux-de-donnees) lists
  the same files as `-fr.xlsx` with French titles; English and French files
  pair by their file name without the `-en`/`-fr` ending (one workbook, the
  2022 occupational therapists, has no French twin).
- Nursing in Canada is on page 1 of that listing (the registered nurses page,
  /en/registered-nurses, only links to it from prose): the earlier probe read
  page 0 alone.
- File sizes by HEAD: 0.1 to 7 MB for every topic workbook, 24.9 MB for the
  NPDB historical utilization 2015-2024, 27.5 MB for the physician supply
  2001-2024 history, 40.3 MB for the NPDB historical utilization 1996-2014.
- Confirmed live 2026-11-24: the two .zip archives are 63.3 MB (NPDB 2022: five
  workbooks, 0.4 to 34.7 MB) and 28.9 MB (physicians 2023: two workbooks). Files
  over the cap are read by parts with range requests, inside the cap (ranged.py):
  every workbook of the archives but the 34.7 MB NPDB 1996-2012 utilization, and the
  1996-2014 workbook without its Table 1 (29.5 MB compressed, 239 MB of XML;
  iterating it alone takes 76 s here, past the 60 s parse budget).
"""

from maplestats_mcp.modules.cihi import constants as cihi_constants

BASE_URL = cihi_constants.BASE_URL
LISTING_URL = f"{BASE_URL}/en/topics/health-workforce/data-tables"
FR_LISTING_URL = f"{BASE_URL}/fr/sujets/main-doeuvre-de-la-sante/tableaux-de-donnees"
LISTING_QUERY = "sort_by=field_published_date_value&sort_order"
# 5 pages of 10 today; a sixth would be a layout change worth stopping at.
LISTING_MAX_PAGES = 12
# A listing page is about 95 KB; a body past this is not that page.
LISTING_MAX_BYTES = 2 * 1024 * 1024
FILE_PATH_PREFIX = "/sites/default/files/document/"
ALLOWED_HOSTS = cihi_constants.ALLOWED_HOSTS

TERMS_URL = "https://www.cihi.ca/en/terms-of-use"
TERMS_URL_FR = "https://www.cihi.ca/fr/conditions-dutilisation"
PERMISSION_EMAIL = "copyright@cihi.ca"

RATE_LIMIT_SOURCE = cihi_constants.RATE_LIMIT_SOURCE
RATE_LIMIT_PER_SECOND = cihi_constants.RATE_LIMIT_PER_SECOND
RATE_LIMIT_CAPACITY = cihi_constants.RATE_LIMIT_CAPACITY
PROVENANCE_SOURCE = "cihi"

CACHE_TTL_LISTING_SECONDS = 24 * 60 * 60
CACHE_TTL_FILE_SECONDS = 6 * 60 * 60
CACHE_TTL_TABLES_SECONDS = 6 * 60 * 60

# The same cap as the indicator workbooks (never raised for this reader): a
# larger file is refused from its declared Content-Length, before any body.
MAX_FILE_BYTES = cihi_constants.MAX_FILE_BYTES

# Rows of a table kept per call; every response is also held to a byte budget.
ROWS_DEFAULT = 50
ROWS_MAX = 500
# A sheet declared larger than this is read for its first table only when the
# tables are listed (a flat database table of 100,000 rows has one table, and
# counting every row would cost 10 to 30 s a call).
LIST_FULL_SCAN_ROWS = 5_000
# Body rows read to tell label columns from value columns, and to see whether
# the header repeats (NPDB tables repeat it for every specialty).
SAMPLE_ROWS = 150
# Notes and text sheets are cut to these sizes.
NOTES_MAX_LINES = 12
NOTE_MAX_CHARS = 700
TEXT_MAX_PARAGRAPHS = 60
TEXT_MAX_CHARS = 1500
TEXT_TOTAL_CHARS = 60_000
NAMES_LISTED_MAX = 40
TABLES_LISTED_MAX = 300
