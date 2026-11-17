### Changed

- The chat demo shows what it is doing while it works: the seconds elapsed, the step it is on
  (planning, finding a tool, reading a source), and the answer as it is written, instead of a
  blank wait until the end. The page now reads `POST /api/chat/stream` (newline-delimited JSON:
  `tool` and `text` events, a `ping` every 10 s while quiet, then one `final` or `error`); the
  guards, limits, counts and answer are the same as `POST /api/chat`, which still works. The old
  note that the first question "can take up to a minute while the data server wakes" is gone: the
  server has been always on since the move to Azure.
- `statcan_census_profile_get_data` and `statcan_census_profile_search_geography` now say how slow
  StatCan's census service is (30 to 45 s for a data call and about 20 s for the first search at a
  level, measured 2026-11-16) and tell a model to make one call per geography level with
  everything it needs in it. A demo answer comparing Kelowna with BC and Canada made three data
  calls (two at one level) and spent about 95 s of its time waiting for this service.
