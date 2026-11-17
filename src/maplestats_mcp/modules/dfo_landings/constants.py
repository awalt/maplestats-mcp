SOURCE = "dfo-landings"
CKAN_PACKAGE_SHOW = "https://open.canada.ca/data/api/action/package_show"
DATASET_PAGE_EN = "https://open.canada.ca/data/en/dataset/{id}"
DATASET_PAGE_FR = "https://ouvert.canada.ca/data/fr/dataset/{id}"

# open.canada.ca package ids (checked 2026-11-08).
SEA_DATASET_ID = "6e16f703-9c57-46c9-9194-6573398c17e6"
FRESHWATER_DATASET_ID = "e426b11c-1dbf-4832-af6f-aa1e52bba574"

# The files are listed by open.canada.ca but served from DFO's own host (checked
# 2026-11-16 in the package_show answers of both datasets). A link to any other host
# is refused rather than fetched.
FILE_HOST = "api-proxy.edh-cde.dfo-mpo.gc.ca"
# No cap existed. 40 MB is what the other CSV readers (shared/csv_files.py, CKAN,
# Alberta) accept; the sea file is a few MB.
MAX_FILE_BYTES = 40 * 1024 * 1024

RATE_LIMIT_PER_SECOND = 2.0
RATE_LIMIT_CAPACITY = 4.0
# The files change about once a year (the sea file's Last-Modified was
# 2026-09-25 on a 2026-11-08 read).
CACHE_TTL_SECONDS = 24 * 60 * 60

DEFAULT_LIMIT = 200
MAX_LIMIT = 2000
# Freshwater is one file per year; cap the files read in one call.
MAX_FRESHWATER_YEARS = 10
