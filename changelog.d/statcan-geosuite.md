### Added

- `statcan_geosuite_` (3 tools): Statistics Canada's Census GeoSuite (92-150-X) for the
  1996, 2001, 2006, 2011, 2016 and 2021 censuses, the geographic attribute tables from
  provinces down to dissemination blocks (enumeration areas in 1996): codes and unique IDs,
  English and French names, the hierarchy, population and dwelling counts, land area and
  representative points. `statcan_geosuite_list_tables` lists a year's tables with row and
  column counts, sizes, source file, licence and attribution; `statcan_geosuite_describe_table`
  gives each column's type, label, code meanings and StatCan field name with sample rows;
  `statcan_geosuite_query` filters one table by exact codes (a trailing `*` matches a prefix)
  and a case- and accent-insensitive name search, with `limit` up to 1,000 and `offset`.
  StatCan's own copy on www12.statcan.gc.ca is behind a Cloudflare bot challenge, so the
  tables are read as Parquet from MountainMath's re-host (data.mountainmath.ca), which
  checked them column by column against StatCan's file; every result says so in
  `provenance.caveats`, with the original file's URL and download date. Each file is
  downloaded once (15.5 MB at most) and queried with DuckDB, which can read that file only.
  `plan_query` routes census geography lookups (codes, UIDs, census tracts, dissemination
  areas and blocks) to it, and to the official 2016 Standard Geographical Classification in
  `rdaas_`.
