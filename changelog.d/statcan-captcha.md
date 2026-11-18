### Added

- `wds_get_full_table_download`: new `file_check` and `notes` fields. The tool
  now asks StatCan for the file's first bytes and says whether a script can
  download it (`downloadable`, `blocked` or `not_checked`). When the file is
  blocked, the notes say how to save it from a web browser and which `wds_`
  tools still give part of the table. Since November 2026 StatCan answers some
  automated full-table downloads with a Cloudflare captcha.
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
- Scripts from `reproduce_code` and `wds_get_full_table_download` that download
  a StatCan file (Python, R, Stata) no longer overwrite a copy saved by hand
  when StatCan answers with its captcha: they read that copy, or stop with the
  link and the steps to get one. The R full-table script explains a failed
  `get_cansim()` the same way.

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
