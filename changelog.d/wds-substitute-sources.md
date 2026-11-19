### Added

- `wds_get_data_from_vectors`, `wds_get_data_from_cube_coord` and `wds_get_series_info`
  answer from another official source when StatCan's Web Data Service answers with the
  Cloudflare challenge and no last good copy of the answer is held. StatCan is always
  asked first; nothing is read from a substitute before WDS has answered or been
  challenged, and nothing tries to get past the challenge. In this order: StatCan's CCEI
  and shared SDMX spaces on api.statcan.gc.ca (table `DF_<product id>`, series found by the
  rows' VECTOR attribute), the Bank of Canada's Valet API for the CPI vectors it carries
  under the same id (`V41690973`, `CPI_MONTHLY`), and the Alberta Economic Dashboard's copy
  of a table (Labour Force Survey rates for Canada, Quebec, Ontario and Alberta, and the
  all-items CPI), always with every column filter. A substitute result keeps the tool's own
  output model and says in `provenance` where it came from: `source` and `url` name the
  host that answered, the new `provenance.substituted_for` is `"wds"`, and the first
  caveat gives, in English or French, which source answered, why, and the newest period.
  It serves published levels only (a `transform` or `frequency` fails with that hint), at
  most 20 series a call, within each source's own caps (the CCEI read's 500 newest rows per
  series, the dashboard's 2,000-row and 200 KB limits, Valet's 200 KB budget; each says so in
  `provenance.limits`). A vector whose table the process does not know (it learns them from
  every WDS answer, and starts with a short list of checked ones) or a coordinate it cannot
  match to a series is listed in `failed`; if nothing can be served the tool raises its own
  error with a "Fix:" naming the CCEI flow and Alberta tables that do hold the table.
  `wds_get_cube_metadata` cannot be substituted (no other source carries WDS member ids),
  and its error says so. `MAPLE_STATCAN_FALLBACK=0` turns all of this off.
- `/stats` counts the answers taken from a substitute, by source, under `fallbacks`.
