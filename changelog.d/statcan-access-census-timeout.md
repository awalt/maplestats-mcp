### Changed

- `statcan_check_access` waits up to 60 seconds for the 2021 Census Profile API
  (20 for every other service) and reports `elapsed_seconds` and `timeout_seconds`
  for each service. The API took 27.7 s on 2026-11-19, so the 20-second wait
  reported a slow service as "no answer". The daily access check prints the
  seconds too.
- The `statcan_census_profile_` tools wait up to 45 seconds, instead of 30, for
  the lists of geographies and characteristics. Slow answers of 23.5 and 27.7
  seconds have been seen, close to the old limit.
