### Security

- `statcan_pumf_tabulate` checked that `url` is a Statistics Canada ZIP link
  only after its first request, so any HTTPS URL was fetched once. The check
  now runs before any request, as it already did for the other PUMF tools.
- `statcan_lode_preview_member` capped the compressed bytes it read but not
  what they inflate to; a small, highly compressed member could fill memory.
  It now stops at 64 MB inflated and reports the preview as partial.
- File tools that take `header_row` (CKAN, Alberta, ECCC Datamart, NWT)
  reject a value above 1,000 before reading; a huge value used to hold the
  whole sheet in memory first.
- ArcGIS service links read from a portal catalogue are checked by host, not
  by a substring: an IP address, `localhost`, a link with credentials, or
  `/rest/services/` only in the query string is refused.

### Fixed

- `wds_get_data_from_vectors` and `wds_get_data_by_reference_period_range`
  with a `transform` or `frequency` sent one request per vector before
  checking the 300-vector limit. The limit is checked first.
- Daily and weekly series aggregated to a lower frequency (Bank of Canada,
  StatCan) lost a complete last or first period when the observations sit
  more than four days from its edge, as weekly Wednesday data do. The
  tolerance now follows the spacing of the observations.
- `statcan_reference_` searches, `statcan_surveys_search_rdc_holdings`,
  `statcan_surveys_search_rtra_datasets` and `statcan_daily_get_releases`
  kept a page that could not be parsed (a maintenance notice answered with
  HTTP 200) in the cache, so they failed for up to a day after StatCan
  recovered. Such a page is no longer cached. The Daily tools also treat an
  HTTP 406 or 409 as an error, not as the page.
- RDaaS tools let a reply that is not JSON out as an untyped error; it is now
  an upstream error.
- `sdmx_get_structure` reported "no such table" for any WDS fault; only a
  table that does not exist says so now.
- `statcan_pumf_tabulate` lost value labels when the data and the codebook
  write a code differently (`01` and `1`).
- `statcan_lode_list_files` failed when one file's link was dead; that file
  now comes back with no size and a note.
- `statcan_census_profile_search_geography`,
  `statcan_census_profile_search_characteristic` and
  `statcan_sdg_search_indicators` ignore accents: "montreal" finds
  "Montréal". The SDG search also labelled every result as cached.
- `statcan_census_profile_archive_get_download_link`: the description said
  only CSV and TAB are covered; 2016 also offers IVT and XML.
- `telecom_prices` tables: a data row whose values all fall between 1990 and
  2100 was read as a year header, dropping the row and mislabelling the rows
  after it.
- `cer_query_file` ignored `start` and `end` on a file with no date or year
  column; it now says so.
- `electricity_quebec_get_facility_flows`: an `end` given as a date alone
  dropped that day's hours after midnight.
- `check_answer` read "per thousand" and "pour mille" as a scale of 1,000,
  and rejected a typeset minus sign ("−3.1") or accounting parentheses as
  not a number.
- `reproduce_code` on a `calc_` tool or `check_answer` wrote a script for an
  unrelated metadata request; it now declines. Generated Julia filters
  matched empty cells as the text "missing", and a NUL character in an
  argument broke generated Python and R scripts.
- CKAN, ArcGIS Hub and Socrata searches and queries: two different requests
  could share one cached answer when an argument held a colon.
- A source with its own licence terms whose file sits on a statcan.gc.ca URL
  (the transit agency list) was labelled with the Statistics Canada licence
  and `commercial_use` "allowed".
- CER and GC InfoBase CSV files with a trailing comma on a data row failed
  with a shape error.
- WFS sources: a blank error text from the server raised an untyped error.
- Python client: a server-sent-events body holding U+2028 or U+0085 inside
  JSON text failed to parse.
- `gazette`, `cihi` and CMHC data-table tools let a malformed XML feed or
  sitemap out as an untyped error (and `gazette` kept the bad feed cached for
  an hour); it is now an upstream error and is not cached.
- `tc_recalls`: a `make` or `model` of only dots (`..`) was normalised out of
  the request path, returning every recall; it is rejected.
- `earthquakes` search: `event_id` with any other filter silently ignored the
  filter; the combination is refused.
- `abs_get_data` dropped the series' unit multiplier, so a value in thousands
  read as units; `unit_multiplier` now carries it.
- `bc_environment`: an impossible date (`2024-13`, `2024-02-31`) passed as a
  bound and silently matched the wrong rows or raised an untyped error; it is
  rejected.
- `oeb_query_dataset`: `year=202` matched 2020 to 2029 by prefix; `year` must
  be a four-digit year.
- `drivebc` events: a `bbox` missed a road segment crossing the box with no
  vertex inside it.
