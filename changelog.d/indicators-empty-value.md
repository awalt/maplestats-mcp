### Fixed

- `statcan_indicators_get_indicators` says when an indicator has no level.
  StatCan's own feeds (`ind-all.json`, `ind-econ.json`, `ind-hp.json`) send
  `value` as an empty string for some indicators and fill only `growth`:
  checked on 2026-11-16, 119 of 2,378 indicators in `all`, 26 of 230 in
  `economic` and 3 of 116 in `homepage`, among them the Consumer Price Index
  (`growth` "3.1%", 12-month change), its components, the price indexes and
  real GDP. The empty text is upstream, not a parsing gap, but nothing said so
  and a reader could take the empty `value` for a missing answer. Now
  `provenance.limits` names the indicators of the result whose `value` is empty
  (in English or French), says that only `growth` is given, and points to the
  series behind them (`source_table`, with `wds_get_cube_metadata` and
  `wds_get_data_from_cube_coord`, or `wds_get_data_from_vectors`; `v41690973`
  for the all-items CPI of Canada). `value` is still a plain string, so the
  output shape is unchanged; the tool's other notes in `limits` now end with a
  full stop, like the other tools' notes.
