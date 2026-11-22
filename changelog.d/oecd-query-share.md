### Changed

- `oecd_query_dataset` may use at most 15 of the server's 50 OECD data downloads an
  hour, so a burst of SQL queries cannot leave `oecd_get_data`,
  `oecd_compare_countries` and the planner without downloads for the rest of the hour.
  Past its share it says when to try again and points to `oecd_get_data`.
