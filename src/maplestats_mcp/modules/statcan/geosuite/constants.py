"""Constants for the Census GeoSuite (92-150-X) tables, read from MountainMath's re-host.

StatCan publishes the GeoSuite (the census geographic attribute tables:
codes, names, hierarchy, population and dwelling counts, land area and
representative points for every standard geography, down to the
dissemination block) as a zip on www12.statcan.gc.ca. That host answers
every automated request with a Cloudflare bot challenge (HTTP 403,
`cf-mitigated: challenge`) since about 2026-10-02, and MapleStats never
tries to pass it (shared/http.py `raise_if_cloudflare_challenge`).

Jens von Bergmann (MountainMath, author of the R package cancensus)
re-hosts the tables as Parquet at data.mountainmath.ca, checked column by
column against StatCan's file (cancensus issue #234, 2026-11-10). Confirmed
live 2026-11-18:

- `{BASE_URL}/{year}/_manifest.json` (HTTP 200 for the six years below, 404
  for any other year and for the bare directory) holds the year's
  provenance (`metadata`: source zip URL and download date, licence,
  attribution, reference guide, build date) and one entry per file
  (`files[]`: path, size, etag, and `metadata` with bilingual titles and
  notes, per-column labels, descriptions, notes and CRS, the primary key,
  `source_check` with rows, columns and the comparison method, and the
  build's `checks`). For 2021 the source is given per file, not per year;
  for 1996 the source is a copy whose download URL was not recorded.
- `{BASE_URL}/{year}/{TABLE}.parquet`: one table per file, 21 (1996) to 31
  (2016, 2021) tables a year; the largest is 2001's DB at 15.5 MB. Codes
  and IDs are text; counts are integers; areas and coordinates doubles.
  Served by Cloudflare with `Accept-Ranges: bytes`, an ETag and
  `Access-Control-Allow-Origin: *`; no challenge.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

BASE_URL = "https://data.mountainmath.ca/census/geo_suite"
ALLOWED_HOST = "data.mountainmath.ca"
YEARS: tuple[int, ...] = (1996, 2001, 2006, 2011, 2016, 2021)

# Where StatCan's own copy lives, for the caveat on every result.
STATCAN_HOST = "www12.statcan.gc.ca"
CLOUDFLARE_SINCE = "2026-10-02"
ISSUE_URL = "https://github.com/mountainMath/cancensus/issues/234"

# One person's server: at most one request a second (a burst of two).
RATE_LIMIT_SOURCE = "statcan-geosuite"
RATE_LIMIT_PER_SECOND = 1.0
RATE_LIMIT_CAPACITY = 2.0

# A year's GeoSuite does not change; the re-host may be rebuilt (a new etag,
# hence a new cached file name), so the manifest is read again daily.
MANIFEST_TTL_SECONDS = 24 * 60 * 60
# Manifests were 255 to 418 KB on 2026-11-18.
MANIFEST_MAX_BYTES = 8 * 1024 * 1024
# The largest table is 15.5 MB (2001 DB); the cap leaves room for a rebuild.
MAX_FILE_BYTES = 64 * 1024 * 1024
# All six years together are about 70 MB, so the cap rarely evicts anything.
CACHE_MAX_BYTES = 256 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 120.0

LIMIT_DEFAULT = 100
LIMIT_MAX = 1000
MAX_FILTER_VALUES = 1000
SAMPLE_ROWS = 3


def cache_dir() -> Path:
    """Where downloaded Parquet files are kept (a few MB each), under the system temp folder."""
    return Path(tempfile.gettempdir()) / "maplestats-mcp" / "geosuite"


def manifest_url(year: int) -> str:
    return f"{BASE_URL}/{year}/_manifest.json"


def file_url(year: int, path: str) -> str:
    return f"{BASE_URL}/{year}/{path}"
