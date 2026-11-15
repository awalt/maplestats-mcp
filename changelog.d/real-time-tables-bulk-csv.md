### Fixed

- `wds_get_full_table_download` no longer refuses the three real-time vintage
  tables 16-10-0118, 16-10-0119 and 20-10-0019 as unknown tables. They are
  missing from WDS's table inventory and metadata, but their full-table CSV zips
  exist (122, 134 and 270 MB; one row per vintage in the `Release` column), and
  the link is returned.

### Changed

- `statcan_delta_list_real_time_tables`: the three tables WDS does not serve
  now carry `bulk_csv_url` and `last_reference_period` (2025-05, 2025-05 and
  2024-08, from the zips' metadata files), and the notes say that only the
  metadata and vector routes are unavailable, that the series ended, and that
  the CSVs are very large and not read row by row by this server.
