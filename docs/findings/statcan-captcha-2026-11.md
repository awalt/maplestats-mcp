# Statistics Canada's captcha (November 2026)

In November 2026 Statistics Canada started answering some automated requests
with a Cloudflare check (HTTP 403, `Cf-Mitigated: challenge`, a "Just a
moment..." page). A person in a web browser can pass it. No script, R or Python
package, or MapleStats can. MapleStats does not try to get past it.

- StatCan announced on Monday 2026-11-16 that it would stop serving full-table
  downloads to automated clients.
- On 2026-11-18 the maintainer of the {cansim} R package reported that
  `get_cansim()` (full tables) fails, while data by vector or by table and
  coordinate still works.
- www12 (census pages) has been behind the same check since October 2026.

## What answers and what does not

Checked live on 2026-11-18 from a cloud host, with this project's client
(HTTP/2, the `maplestats-mcp` User-Agent). Which paths are checked can differ
by network and by day: the full-table zips downloaded from this host but not
from the {cansim} maintainer's.

| Path on www150.statcan.gc.ca | What it serves | Answered a script? |
|---|---|---|
| `/t1/wds/rest/` | Web Data Service (WDS) JSON API | Yes |
| `/n1/tbl/csv/`, `/n1/tbl/sdmx/` | Full-table zips | Yes from here, no for {cansim} |
| `/n1/delta/` | Delta File zips | Yes |
| `/n1/pub/.../*.zip` | PUMF and LODE files | Yes |
| `/n1/daily-quotidien/` | The Daily's articles | Yes |
| `/n1/dai-quo/ssi/` | Release schedule and archive JSON | Yes |
| `/t1/tbl1/` | Table viewer pages | Yes |
| `/t1/wds/sdmx/` | SDMX REST API | No |
| `/t1/cimt/` | Trade by HS commodity (CIMT) API | No |
| `/n1/rss/` | The Daily's RSS feeds | No |
| `/n1/en/...`, `/n1/pub/...` pages | Catalogue, search, publication pages | No |

## What MapleStats does about it

- **Every error from a blocked page says what happened and what still works.**
  `shared/challenge_notes.py` adds a note to the "unavailable" error: StatCan's
  change (not a MapleStats fault), that the `wds_` tools still answer, and the
  closest route for that path.
- **One blocked path no longer cuts off the rest of the host.** The circuit
  breaker used to count a challenge as a failure, so a few SDMX calls in a row
  could open www150's breaker and refuse every WDS call for a minute. A
  challenge is now counted in `/stats` only.
- **`sdmx_` tools read the same series from WDS.** When SDMX answers with the
  check, `sdmx_get_data` and `sdmx_get_vector_data` turn the key into WDS
  coordinates (a wildcard takes every member, up to 300 series per call) and
  ask WDS for the latest N periods or a reference-period range.
  `sdmx_get_structure` and `sdmx_get_key_for_dimension` build the codelists
  from WDS metadata. Each result says so in its provenance.
- **`statcan_daily_get_releases` reads the release archive** when the RSS feed
  is blocked, for `subject="all"`: titles, dates and article links, with the
  reference period as the summary. One subject still errors, and the error
  points to `subject="all"` and `statcan_daily_search_archive`.
- **`wds_get_full_table_download` checks its link.** It asks for the file's
  first four bytes and returns `file_check` (`downloadable`, `blocked` or
  `not_checked`) and `notes`: how to save the file from a browser into
  `data/raw/`, and which `wds_` tools give part of the table without one.
- **Scripts for StatCan files keep working with a saved copy.** Python, R and
  Stata scripts that download a StatCan file check for the captcha before
  writing, so a refused download never overwrites a copy saved by hand. They
  read that copy, or stop with the link and the steps to get one. The R script
  for a full table wraps `get_cansim()` with the same message.

## What has no workaround

- **Trade by HS commodity (`cimt_`).** The errors name the closest WDS tables:
  12-10-0011-01, 12-10-0163-01 and 12-10-0175-01 (monthly), and 12-10-0171-01
  to 12-10-0173-01 (annual, by HS product section).
- **Catalogue, search and publication pages** (`statcan_reference_`,
  `statcan_pumf_search`, `statcan_pumf_list_files`, `statcan_lode_list_databases`).
  Tables are still found through `wds_search_cubes`. PUMF and LODE files still
  download when their link is known.
- **Full tables, where the zip is blocked.** A person downloads the file in a
  browser. The `wds_` series tools give part of a table automatically.
