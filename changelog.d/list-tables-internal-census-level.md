### Added

- `ab_economic_list_tables`: each table has an `internal` flag, true for the
  dashboard's own working tables (its index and lookup tables, `_stage` copies that
  stopped updating, `Defence_*` project lists), and these come after the published
  tables. `_SQL` tables are not marked: some are the live copy of a StatCan table.
  Issue #265.
- `statcan_census_profile_search_geography`: `level` is now optional. Without it, a
  province, territory or "Canada" by name is searched at the provinces level, an FSA
  (T5J) at the FSA level and any other name as a municipality (census subdivision),
  and the result's `provenance.coverage` says which level was used. An empty query
  without a level is refused with the levels to choose from. Issue #273.
- After each deploy to Azure, `docker.yml` runs the live module steps of
  `scripts/smoke_test_modules.py --url` against the new revision (`check-azure-live`),
  so a source that answers Azure differently shows up the same day.
