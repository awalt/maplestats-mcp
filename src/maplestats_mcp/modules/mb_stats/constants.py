"""Constants for the Manitoba Bureau of Statistics module.

Checked live on 2026-11-24 against www.gov.mb.ca/mbs/:

- The Bureau's pages are built in the browser from two CSV files that its
  scripts read with PapaParse: `_asset/api/manitoba_quick_facts.csv` (the
  indicator tiles: Id, Title, Category, Reference Period, Value, Data Type,
  Change, chgDirection, chgContext, powerBI_link, SummaryText, SubCategory,
  CategoryOrder, SubCategoryOrder, TileOrder, IsKeyIndicator) and
  `_asset/api/mbs_report.csv` (1,146 rows: FileName, Date Released,
  displayName, Related_indicatorId, ReportType). SummaryText holds unquoted
  commas, so a row splits into 16 to 19 fields, and two notes on Labour Force
  Survey revisions break across lines; the first ten and the last five fields
  are reliable and the rest is the summary.
- ReportType is Bulletin, Data Table, Report, Infographic, Related links,
  Winnipeg and Non-Winnipeg (electoral division profiles), Map, Aggregate and
  Methodology. Data tables (213 rows, 150 distinct files, all .xlsx) and PDFs
  sit at /mbs/publications/<FileName>; a "Related links" row's FileName is a
  full URL (mostly Statistics Canada tables). One file can be listed under
  several indicators.
- Licence: the OpenMB Information and Data Use Licence, named on
  gov.mb.ca/legal/copyright.html ("for both commercial and non-commercial
  purposes", with attribution).
- robots.txt (www.gov.mb.ca) disallows everything to named AI crawlers and
  agents (GPTBot, ChatGPT-User, anthropic-ai, ClaudeBot, Claude-Web and
  others) and, for every other user agent, only a list of old expense files
  and internal paths, none under /mbs/. This module identifies itself with
  the project's own User-Agent; see docs/findings/provincial-sources.md.
"""

DOMAIN = "www.gov.mb.ca"
SITE = f"https://{DOMAIN}"
MBS_URL = f"{SITE}/mbs/index.html"
QUICK_FACTS_URL = f"{SITE}/mbs/_asset/api/manitoba_quick_facts.csv"
REPORTS_URL = f"{SITE}/mbs/_asset/api/mbs_report.csv"
PUBLICATIONS_PATH = "/mbs/publications/"
PUBLICATIONS_URL = f"{SITE}{PUBLICATIONS_PATH}"
INDICATOR_PAGE_URL = f"{SITE}/mbs/moreinfo.html?id={{id}}"

RATE_LIMIT_SOURCE = "mb-stats"
RATE_LIMIT_PER_SECOND = 1.0
RATE_LIMIT_CAPACITY = 3.0

CACHE_TTL_LIST_SECONDS = 2 * 60 * 60
CACHE_TTL_FILE_SECONDS = 6 * 60 * 60

MAX_LIST_BYTES = 5 * 1024 * 1024
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_ROWS_PER_SHEET = 20000
ROWS_LIMIT_DEFAULT = 50
ROWS_LIMIT_MAX = 500
HEADER_ROWS_MAX = 5
FILES_LIMIT_DEFAULT = 40
FILES_LIMIT_MAX = 200
SUMMARY_CHARS = 400

PROVENANCE_SOURCE = "manitoba-bureau-of-statistics"
