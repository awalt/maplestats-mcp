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
- **Scripts only where a script can work.** `reproduce_code` writes scripts
  for StatCan's Web Data Service (vectors, coordinates, reference-period
  ranges), which StatCan still serves. `wds_get_data_from_cube_coord` and the
  other `wds_` tools now replay their WDS request; they used to download the
  whole table's zip. For a blocked service (SDMX, CIMT, RSS feeds, catalogue
  pages, www12) and for full-table zips, it writes no script and says why
  (`shared/challenge_notes.script_refusal`). Scripts never rely on a file
  saved by hand.
- **`wds_get_full_table_download` gives the link for a browser, with no
  script.** StatCan announced it blocks automated full-table downloads, so a
  script built on the file could stop working at any time, even where it
  downloads today. `file_check` says what the link served just now, and
  `notes` name the WDS tools a script can use. Its `members`, `start_period`
  and `end_period` arguments, which only filtered the scripts, are gone.
- **No `get_cansim()`.** The R scripts used it only for full tables. The
  {cansim} vector functions (`get_cansim_vector_for_latest_periods`) read WDS
  and still work, so the R vector scripts keep them.
- **Scripts that download a StatCan file that still works** (PUMF and LODE
  zips, the Delta File) stop with a plain message if StatCan answers with the
  captcha, instead of failing later on a "bad zip".
- **Scripts name themselves.** They send "MapleStats MCP reproduction script"
  as their User-Agent, never a browser-like one.

## What has no workaround

- **Trade by HS commodity (`cimt_`).** The errors name the closest WDS tables:
  12-10-0011-01, 12-10-0163-01 and 12-10-0175-01 (monthly), and 12-10-0171-01
  to 12-10-0173-01 (annual, by HS product section).
- **Catalogue, search and publication pages** (`statcan_reference_`,
  `statcan_pumf_search`, `statcan_pumf_list_files`, `statcan_lode_list_databases`).
  Tables are still found through `wds_search_cubes`. PUMF and LODE files still
  download when their link is known.
- **Full tables.** A person downloads the file in a browser. The `wds_`
  series tools give up to 300 series per call automatically.
