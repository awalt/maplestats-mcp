### Added

- `/stats`: `last_7_days`, the past week's calls, failures by code, top failing tools
  and clients, counting callers only: the maintainer's internal, Maple Test and
  uptime-check calls are left out of the counts (`by_client` still lists them). The
  all-time totals mixed in failures from before error codes and calls from before
  client labels: on 2026-11-23 a third of failures were "uncoded" and two thirds of
  calls "untracked". `daily` gives the five top failing tools' calls and failures
  per day, to see whether a fix landed. The per-tool daily counts are saved to
  `MAPLE_USAGE_STATS_FILE` (`by_day_tool`, 35 days); older files load unchanged.
- `/stats`: `unknown_tool_closest`, calls to a tool name that does not exist, counted
  under the registered tool closest to it (or `no_close_match`). The name a caller
  sent is never kept.
