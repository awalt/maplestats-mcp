### Fixed

- `nrcan_fuel_prices_get_prices`: with `latest_n` and no `year`, only the current year's page
  was read, so `latest_n=1` failed with "no prices" in January (for weekly prices, until the
  first Tuesday) and, for monthly prices, `latest_n=12` in March returned two periods with no
  word about it. When the current year has fewer periods than `latest_n` (and the prices are
  not daily), last year's page is read as well, its short cache time being that of the
  current year because December's figures are posted in early January. A period listed on
  both pages is kept once, and the latest `latest_n` periods are returned. `provenance.coverage`
  names both pages, and the result's `year` is now the year of the page the latest rows come
  from (last year when this year's page had none). When fewer periods exist than were asked
  for, the result's `note` says how many there are and, if last year was read, to pass `year`
  for earlier ones. Reading goes back one year at most.
- `ckan_datastore_search`: it took a bare resource id and never applied the CanadaBuys
  exclusion that `ckan_get_dataset`, `ckan_get_resource`, `ckan_read_resource` and
  `ckan_describe_resource` apply, so CanadaBuys rows could still be read through it. It now
  looks the resource up first (the same cached `resource_show` that `ckan_get_resource` uses)
  and refuses a resource whose dataset or URL is excluded, with the same message. A reply
  that is not a resource record is refused with an upstream error instead of reading rows,
  and a DataStore alias that the portal's resource lookup does not know is refused as not
  found, where it used to read rows.
- `disclosure_summarize`: for contracts grouped by `fiscal_year` or `quarter`, an agreement
  that had been amended counted wholly in the period of its latest row (a contract first
  published in 2019-2020 and amended in 2023-2024 sat in 2023-2024), the `fiscal_year` filter
  read only the rows published in that fiscal year, and `date_from` and `date_to` keep rows by
  their contract date before the latest row is chosen. The summary's `method` now states
  these rules, in English and French, when they apply; the figures are unchanged.
- `disclosure_search_contracts`, `disclosure_search_grants`, `disclosure_search_travel`,
  `disclosure_search_hospitality` and `disclosure_summarize`: an amount written with a
  decimal comma ("38900,25", "1 200,50", or with the currency sign after the number,
  "38900,25 $") was read 100 times too large because every comma was dropped, and one decimal
  digit ("0,5") was read 10 times too large. With no period in the value, one or two digits
  after the last comma are now decimals, since a thousands group has three; "1,200",
  "1,200,000" and "1,200.50" read as before.
- `transit_get_stop_departures` and `transit_get_route_summary`: trips defined in
  `frequencies.txt` are not listed (their stop times are templates, and headways are not
  expanded), and nothing said so, so a stop or route served only by them read as having no
  service. `provenance.limits` now says how many such trips were left out, in English and
  French; a trip whose service ran the day before counts only if its window runs past
  24:00. `transit_get_stop_departures` also gave an English error for a bad `start_time`
  on a French call; it is now in French.
- `elections_financial_returns_*`: one cookie jar served every call, and the portal keeps the
  selected candidate in that session, so two calls at the same time could take turns in the
  middle of each other's select, redirect and download and return one candidate's report for
  another. The search, the report download (retry included) and the election list now take
  turns on the portal session, so one slow download makes the others wait. A downloaded
  report whose `Client_id` rows name a different candidate than the one asked for is refused
  with an upstream error instead of being returned and cached.
- `ab_wildfire_*` (`forest_area`, `fire_number`, `name_contains`), `eps_*`
  (`intersection_contains`) and `cbsa_tariff_search`: `%` and `_` in the text were SQL `LIKE`
  wildcards, so `%` matched every row and `ma_le` matched "maple". They now match themselves:
  the ArcGIS searches add `ESCAPE '$'` only when the text holds a wildcard, and the tariff
  search escapes them for DuckDB.
- `socrata_query_dataset_rows`: a 200 answer that was not a list of rows (an error document
  or a gateway page) came back as "0 rows"; it now raises an upstream error. A page after the
  first (`offset` above 0) with no `order` is now ordered by the row id (`:id`), and
  `provenance.limits` says so; the first page is sent as before and has no fixed order, so
  pass `order` on every page for stable paging. Grouped, aggregate and `distinct` queries get
  no default order.
