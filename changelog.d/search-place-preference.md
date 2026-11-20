### Changed

- `search_tools` prefers tools for the place a query names. A tool for one city or
  province ranks lower (its score halved) when the query names other places, and a
  foreign publisher's tool (`fed_`, `ecb_`, `eurostat_`, `ons_`, `abs_`, `cdc_`) ranks
  lower unless the query names that publisher or its country, in English or French.
  A query about Canada as a whole scales one province's tools by 0.7, and a query
  that names no place by 0.9. Before, "Interest rates in Canada" and "USD to CAD
  exchange rate" put the US Federal Reserve above the Bank of Canada, and "Manitoba
  school divisions" put an Alberta tool first. The website's tool search ranks the
  same way. On the discovery benchmark, search MRR went from 0.661 on 0.7.0 to
  0.685 with this release's new sources, recall at 5 from 0.837 to 0.868; one
  query moved from rank 9 to 10.
