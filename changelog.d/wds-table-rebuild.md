### Added

- `wds_get_full_table_download` (CSV) returns a Python script that rebuilds the
  whole table through WDS, which StatCan still serves to scripts, now that it
  blocks scripted full-table downloads. The script asks for every series in
  batches and writes StatCan's own CSV layout; checked byte for byte against
  StatCan's file on 2026-11-18 for 36-10-0104 (whole), 18-10-0004 and
  14-10-0287. `members`, `start_period` and `end_period` keep part of a table,
  and a new `rebuild` field gives its size in WDS calls; past 2,000 calls there
  is no script and the notes say how to narrow it. The idea comes from
  vrraiv/sixfigures (PR #105); the code is MapleStats' own.
