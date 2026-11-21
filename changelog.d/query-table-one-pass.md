### Fixed

- `wds_query_table` reads a full-table file in one download when StatCan's file
  servers stop honouring range requests. After StatCan's outage of 2026-11-21 they
  answered five ranged requests in six with the whole file, and the tool failed with
  "reports no size, so it cannot be read by range". It now walks the zip in order and
  inflates only the data CSV, with the same size and time limits; a dropped download is
  reported as unavailable, to retry. Checked live: the CPI and LFS slices came back
  identical by either route (LFS: 17 s by range, 47 s in one pass).
- `scripts/smoke_test_statcan_wds.py` skips only the changed-series steps when StatCan
  answers them with HTTP 409 (overnight, and on days with no release); it used to stop
  there and leave every later step unchecked.
