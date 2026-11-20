### Added

- `/stats` gives `top_failing_tools`: the 20 tools with the most failed calls, most
  first, each with its calls, failures, error rate and failures by code (`not_found`,
  `invalid_input`, `upstream_unavailable`, `upstream_error`, `unknown_tool`, ...), so
  the questions MapleStats cannot answer show at a glance. It is computed from the
  counts `/stats` already keeps (`by_tool` and `by_error`), so `MAPLE_USAGE_STATS_FILE`
  keeps its format and older files load as before; failures counted before error codes
  were kept show as `uncoded`.
