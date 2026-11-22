### Fixed

- `scripts/smoke_test_statcan_wds.py` also skips the changed-cube step when StatCan
  answers HTTP 409 on a day with no release; on a weekend the run stopped there.
