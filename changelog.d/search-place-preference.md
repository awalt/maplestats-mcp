### Changed

- `search_tools` prefers tools for the place a query names. A tool for one city or
  province ranks lower (its score halved) when the query names other places, and a
  foreign publisher's tool (`fed_`, `ecb_`, `eurostat_`, `ons_`, `abs_`, `cdc_`) ranks
  lower unless the query names that publisher or its country. A query about Canada
  as a whole that names no province scales one province's tools less (0.7). Before,
  "Interest rates in Canada" and "USD to CAD exchange rate" put the US Federal
  Reserve above the Bank of Canada, and "Manitoba school divisions" put an Alberta
  tool first. On the discovery benchmark with this release's new sources, search
  MRR went from 0.669 to 0.684, recall at 1 from 0.543 to 0.558, and no query
  ranked lower; place matching reuses `plan_query`'s.
