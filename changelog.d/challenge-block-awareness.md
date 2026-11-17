### Changed

- A Cloudflare challenge is reported as a block, not an outage. On 2026-11-17, from about 18:25 UTC,
  Statistics Canada's `www150.statcan.gc.ca` host answered every automated client with a managed
  challenge (HTTP 403, `Cf-Mitigated: challenge`, a page titled "Vérification de sécurité / Security
  Check"), and every `wds_*`, `sdmx_*`, `cimt_*`, `statcan_daily_*` and similar tool failed with a
  message that said to "retry once in a minute". The error now says, in English and French, not to
  retry, that the host is challenging automated clients, since what time (UTC), and which sources
  still answer: the census profile and the CCEI and shared SDMX spaces on `api.statcan.gc.ca`,
  `geo.statcan.gc.ca`, the Bank of Canada, CMHC, the provincial modules and the OECD. The code stays
  `upstream_unavailable`, and `CloudflareChallenge` is still an `UpstreamUnavailable`, so nothing that
  catches it changes; it gains a `host` attribute. The circuit breaker's refusal while the host is
  paused names the challenge and the time it began instead of "timeouts, connection errors or server
  errors", and the generic hint for a challenge raised by any other module no longer says to retry.
- While a host answers with a Cloudflare challenge, the circuit breaker waits longer after each failed
  probe: 60 s, 5 min, 15 min, then 30 min (1, 5, 15 and 30 times `MAPLE_BREAKER_COOLDOWN_SECONDS`), and
  never more than 30 minutes (or the configured cooldown, if that is longer), so a policy block is not
  probed every minute. Timeouts, connection errors and 5xx answers keep the base cooldown.

### Added

- `/stats` `upstreams.hosts[host]` gains `cause` (`challenge`, `timeout`, `network` or `server_error`;
  `null` while the breaker is closed), `blocked_since` (UTC, when that cause first failed) and
  `cooldown_seconds`, beside the existing `state` and `probe_after` (the next probe); `upstreams.breaker`
  gains `challenge_cooldown_max_seconds`. The `docs://status` resource shows the cause and the start time
  of each paused host in English and French, and for a challenge says not to retry and what still works.
  The state is per process and starts empty after a restart.

### Fixed

- The page check that runs when a 403 carries no `Cf-Mitigated` header now also recognises StatCan's own
  challenge page by its title ("Security Check" or "Vérification de sécurité"), not only "Just a moment";
  a challenge that arrived without the header used to surface as a plain 403 error.
