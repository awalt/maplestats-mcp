### Fixed

- `elections_results_get_historical_candidates` and
  `elections_results_get_historical`: a province code such as `province="AB"`
  matched inside "Newfoundland and Labrador" and returned Newfoundland rows.
  Postal codes, SGC codes ("48") and French names now name their province.
- `statcan_daily_get_article`: a release date ("2026-11-04") or a release title
  is now looked up in The Daily's archive; a title reads the newest matching
  release, and a date with several articles lists their ids. Both were refused
  as invalid input before (27 of 69 calls in `/stats`).
- `statcan_census_profile_get_data`: a Canada or province code ("01", "48",
  "AB") is taken as its 2021 DGUID instead of being refused for an unknown
  geography level.

### Changed

- The hosted server's per-caller rate limit is 120 requests a minute, set in the
  deploy workflow; the Azure app had 60 set by hand.
