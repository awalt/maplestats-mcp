### Fixed

- `nl_opendata_search_datasets`: a page that is not the
  Newfoundland and Labrador portal's own (a maintenance or block page, served once to
  the hosted server on 2026-11-19) now reads as the source being unavailable, to retry
  shortly, instead of an upstream error. The portal's own page without its dataset
  list still reads as an upstream error, since that means its layout changed.

### Changed

- `scripts/smoke_test_modules.py --url <endpoint>` runs the same live steps against a
  hosted server, one session per call and spaced under its rate limit, so a deploy can
  be checked on its own network. The `reproduce_code` step for `sdmx_get_data` now
  expects no script and StatCan's refusal note; Excel Power Query is checked on a Bank
  of Canada series instead.
