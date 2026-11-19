### Added

- The weekly live smoke run now fails loudly when one upstream host took many scripts down. A script cut
  short by an outage (exit 75) used to be a warning and `exit 0`, so a whole host going dark looked healthy:
  when StatCan's `www150.statcan.gc.ca` began answering automated clients with a Cloudflare challenge on
  2026-11-17, a dozen scripts skipped and the run stayed green. A skipped script now prints the host or hosts
  behind its outage (`SKIPHOST <host> <script>`, read from the failing httpx error or, failing that, from
  the circuit breaker's error counts), and a new `skipped hosts` job in `smoke.yml` runs
  `scripts/check_skipped_hosts.py`: more than 3 scripts skipped for the same host in one run, or the same
  host skipped in the previous run too (kept as the `smoke-skipped-hosts` artifact), fails the run, and the
  alert job puts the host and its scripts in the smoke-failure issue. One script skipping for one host, once,
  still never turns the run red.
- The chat demo shows a short notice, in English and French, while the MCP server reports that StatCan
  answered automated requests with its bot check in the last 15 minutes: "StatCan's data service is
  temporarily refusing automated requests; some answers may be unavailable or come from other sources". The
  page asks a new `GET /api/status` (`{"upstream_blocked": true|false}`) on load and every minute; the chat
  service reads the MCP server's `/stats` `upstreams.challenged_paths` at most once a minute, ignores a
  failed read, and never lets it hold up a question. The notice appears once the MCP server reports
  `challenged_paths`.
