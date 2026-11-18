"""The StatCan services statcan_check_access tries, each with one cheap request.

Since November 2026 Statistics Canada answers some automated requests with a
Cloudflare check only a person in a browser can pass, and which paths it checks
has changed from day to day (WDS itself was challenged overnight on 2026-11-17,
per two outside projects). Each entry is one request a MapleStats tool makes,
small enough to send on every check: a Range request for files and pages (a
server that ignores Range is cut off at MAX_BYTES), and the smallest WDS POSTs.
Endpoints checked live from a cloud host on 2026-11-18.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

WWW150 = "https://www150.statcan.gc.ca"

# Bytes read from an answer at most; past it the answer still counts as served.
MAX_BYTES = 64 * 1024
TIMEOUT_SECONDS = 20.0
CACHE_TTL_SECONDS = 15 * 60
CONCURRENCY = 4


@dataclass(frozen=True)
class Endpoint:
    key: str
    name_en: str
    name_fr: str
    url: str
    tools: str  # the MapleStats tools that use it
    post_json: Any = None
    headers: dict[str, str] = field(default_factory=dict)


ENDPOINTS: tuple[Endpoint, ...] = (
    Endpoint(
        "wds_metadata",
        "WDS table metadata (getCubeMetadata)",
        "Métadonnées des tableaux du WDS (getCubeMetadata)",
        f"{WWW150}/t1/wds/rest/getCubeMetadata",
        "wds_get_cube_metadata, wds_get_full_table_download",
        post_json=[{"productId": 36100104}],
    ),
    Endpoint(
        "wds_vectors",
        "WDS series by vector",
        "Séries du WDS par vecteur",
        f"{WWW150}/t1/wds/rest/getDataFromVectorsAndLatestNPeriods",
        "wds_get_data_from_vectors, wds_get_data_from_cube_coord, sdmx_",
        post_json=[{"vectorId": 2062815, "latestN": 1}],
    ),
    Endpoint(
        "full_table_csv",
        "Full-table CSV files (/n1/tbl/csv/)",
        "Fichiers CSV des tableaux complets (/n1/tbl/csv/)",
        f"{WWW150}/n1/tbl/csv/36100104-eng.zip",
        "download_url of wds_get_full_table_download",
        headers={"Range": "bytes=0-3"},
    ),
    Endpoint(
        "sdmx",
        "SDMX REST service",
        "Service REST SDMX",
        f"{WWW150}/t1/wds/sdmx/statcan/rest/data/DF_36100104/1.1.1.1?lastNObservations=1",
        "sdmx_ (which fall back to WDS)",
    ),
    Endpoint(
        "cimt",
        "Trade by HS commodity (CIMT)",
        "Commerce par marchandise du SH (CICM)",
        f"{WWW150}/t1/cimt/rest/getPeriods",
        "cimt_",
        headers={"Referer": f"{WWW150}/n1/pub/71-607-x/2021004/exp-eng.htm"},
    ),
    Endpoint(
        "daily_rss",
        "The Daily's RSS feeds",
        "Fils RSS du Quotidien",
        f"{WWW150}/n1/rss/dai-quo/0-eng.atom",
        "statcan_daily_get_releases (falls back to the archive for all subjects)",
        headers={"Range": "bytes=0-1023"},
    ),
    Endpoint(
        "daily_archive",
        "The Daily's release archive and schedule",
        "Archive et calendrier des diffusions du Quotidien",
        f"{WWW150}/n1/dai-quo/ssi/homepage/schedule-previous_releases-eng.json",
        "statcan_daily_search_archive, statcan_daily_get_release_calendar",
        headers={"Range": "bytes=0-1023"},
    ),
    Endpoint(
        "indicators",
        "Indicators feed",
        "Fil des indicateurs",
        f"{WWW150}/n1/dai-quo/ssi/homepage/ind-hp.json",
        "statcan_indicators_get_indicators",
    ),
    Endpoint(
        "catalogue_search",
        "Data catalogue search and publication pages",
        "Recherche du catalogue et pages de publications",
        f"{WWW150}/n1/en/type/data?text=unemployment",
        "statcan_reference_, statcan_pumf_search, statcan_lode_list_databases",
        headers={"Range": "bytes=0-1023"},
    ),
    Endpoint(
        "pumf_file",
        "Public use microdata files (PUMF zips)",
        "Fichiers de microdonnées à grande diffusion (zip)",
        f"{WWW150}/n1/pub/71m0001x/2021001/2026-10-CSV.zip",
        "statcan_pumf_list_zip, statcan_pumf_tabulate",
        headers={"Range": "bytes=0-3"},
    ),
    Endpoint(
        "census_profile_api",
        "2021 Census Profile API (api.statcan.gc.ca)",
        "API du Profil du recensement de 2021 (api.statcan.gc.ca)",
        "https://api.statcan.gc.ca/census-recensement/profile/sdmx/rest/codelist/STC_CP/CL_GEO_PR/latest",
        "statcan_census_profile_",
    ),
    Endpoint(
        "rdaas",
        "RDaaS classifications (api.statcan.gc.ca)",
        "Classifications RDaaS (api.statcan.gc.ca)",
        "https://api.statcan.gc.ca/rdaas/search/classifications?q=NAICS",
        "rdaas_",
    ),
    Endpoint(
        "census_www12",
        "Census site (www12)",
        "Site du recensement (www12)",
        "https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/index.cfm",
        "census pages and files (statcan_geosuite_ reads a re-hosted copy instead)",
        headers={"Range": "bytes=0-1023"},
    ),
)
