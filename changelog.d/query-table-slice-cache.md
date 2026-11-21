### Changed

- `wds_query_table` keeps the slice it read in memory for 15 minutes, so a follow-up
  query on the same table, members and periods (another SQL) skips the download: about
  16 s for the Labour Force Survey table. The key is the table, its release time, the
  members and the periods, never the SQL, so a new release reads the table again; at
  most 300,000 rows are kept across slices, the oldest going first, and nothing is
  written to disk. A result read from memory says so in `provenance` (`cached` and
  `coverage`). Slices now hold each repeated member name, title and period once.
