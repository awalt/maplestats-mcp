### Added

- `wds_query_table`: one read-only SQL query over a whole StatCan table, or a slice
  of it (`members`, `start_period`, `end_period`), for questions across more
  series than `wds_query_series` holds. The server reads the table's full-table
  CSV as it downloads (tables up to 200 MB zipped; nothing written to disk),
  keeps the rows asked for (at most 300,000) and runs the query with DuckDB over
  `obs`: the `wds_query_series` columns plus one per dimension. It runs the same
  checks as `wds_query_series` (a misspelled member is refused before the
  download). Where StatCan answers the file with its captcha, the slice is
  rebuilt from WDS by coordinate, with the same rows (checked live on
  2026-11-20). The LFS table (1.2 GB of CSV) took about 16 s at a 158 MB peak.
  Off where `MAPLE_QUERY_SERIES` is off, like `wds_query_series`.

### Fixed

- `wds_get_full_table_download` raised a raw ValueError for a year-only
  `start_period` ("2025"), a form its description gives.
