### Fixed

- `cimt_`: since 2026-11-17 StatCan's Cloudflare check has blocked scripts from the CIMT
  code lists (`/n1/pub/71-607-x/`), while the trade service itself still answers. As a
  result `cimt_get_trade`, `cimt_get_top_partners` and `cimt_get_province_breakdown`
  failed outright. They now return the trade values with codes in place of the names
  that could not load, and the reply says which names are missing. Provinces are
  always named, from the SGC names. A partner given as `US` or as a numeric code
  still resolves. A partner given by name, and both search tools, now say what to
  use instead (`cbsa_tariff_search` for HS codes).
- `statcan_check_access` now also checks the CIMT code lists, so it reports this
  block.
- `cimt_`: while `/n1/pub/` is known to be challenged (within `path_health`'s 15
  minutes), a code list that is not already cached is not requested again. On
  2026-11-24, after repeated challenged requests from one address, StatCan challenged
  that address on all of www150, the Web Data Service included.
