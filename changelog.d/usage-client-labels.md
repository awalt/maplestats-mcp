### Added

- `/stats` now says what kind of client made the calls: `by_client` (and `by_day_client`
  per UTC day) count calls under a label from a fixed list (`claude-code`, `claude-ai`,
  `cursor`, `codex`, `python-fastmcp`, `uptime-check`, ... or `other`), matched from the
  name the client announces when it connects. The announced name itself, arguments and
  addresses are still never stored, and nothing new is sent to GoatCounter. Counts from
  before this change show as `untracked`. They are saved in `MAPLE_USAGE_STATS_FILE`.
- `MAPLE_INTERNAL_TOKEN`: a client that sends this secret in an `X-Maple-Internal` header
  is counted as `internal`, and `/stats` gives `calls_excluding_internal`, so the
  maintainer's own calls and benchmark runs can be told apart from everyone else's.
  `tests/maple_test` sends the header when `MAPLE_INTERNAL_TOKEN` is set in its environment.
- The privacy page says that `/stats` records the kind of client.
