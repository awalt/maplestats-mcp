### Added

- `wds_get_full_table_download`: new `file_check` and `notes` fields. The tool
  asks StatCan for the file's first bytes and says whether the link served the
  file or the captcha just now, and the notes name the WDS tools a script can
  still use.
- Every error from a StatCan page behind the captcha now says it is StatCan's
  change (not a MapleStats outage), that the `wds_` tools still answer, and the
  closest route for that page (WDS tables for CIMT trade, the release archive
  for The Daily's feeds, a browser download for files). Details in
  `docs/findings/statcan-captcha-2026-11.md`.

### Changed

- `sdmx_get_data`, `sdmx_get_vector_data`, `sdmx_get_structure` and
  `sdmx_get_key_for_dimension`: when StatCan's SDMX service answers with its
  captcha (every request since 2026-11-18 from the networks checked), they read
  the same series and codes from WDS and say so in provenance. A key that
  covers more than 300 series is refused with the dimension to narrow.
- `statcan_daily_get_releases`: with `subject="all"`, reads the latest releases
  from The Daily's release archive when its RSS feed answers with the captcha.
- `reproduce_code` writes scripts only where a script can work: StatCan's Web
  Data Service. `wds_get_data_from_cube_coord` (without a transform) and the
  other `wds_` tools now fetch their series through WDS instead of downloading
  the whole table's zip. For a service StatCan blocks (SDMX, CIMT, The Daily's
  RSS feeds, catalogue pages, www12) and for full-table zips, it returns no
  script and says why. R scripts no longer use `get_cansim()`; the {cansim}
  vector functions stay.
- Scripts that download a StatCan file that still works (PUMF and LODE zips,
  the Delta File) stop with a plain message if StatCan answers with its captcha.

### Removed

- `wds_get_full_table_download`: the `members`, `start_period` and
  `end_period` arguments and the `scripts` field. Since November 2026 StatCan
  blocks automated full-table downloads, so the tool gives the link for a
  person to open in a browser and writes no script. For data a script can
  fetch, use `wds_get_data_from_cube_coord`, `wds_get_data_from_vectors` or
  `wds_get_data_by_reference_period_range`, and `reproduce_code` on them.

### Fixed

- A Cloudflare challenge no longer counts toward opening a host's circuit
  breaker (it still shows in `/stats`). StatCan challenges SDMX and CIMT on
  www150 while WDS on the same host answers, so a few blocked calls in a row
  used to refuse every WDS tool for a minute.

### Security

- Python scripts from `reproduce_code` now identify themselves as "MapleStats MCP
  reproduction script" with the project's address, instead of a browser-like
  User-Agent (`Mozilla/5.0 (compatible; research script)`). No MapleStats code
  poses as a web browser. The old value is kept, unused, in
  `reproduce/render.py` as a record.
