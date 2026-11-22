### Added

- `/stats` → `rate_limit` shows whether the per-client rate limit tells callers apart
  behind a proxy: the shape of `X-Forwarded-For` on MCP requests (how many entries,
  and whether the last is a private address) and the most callers the limit held at
  once. Never an address. On Azure the live check still met 18 refusals at 75 requests
  a minute with `MAPLE_TRUST_PROXY_HEADERS` on (2026-11-22), a sign that the last
  entry is an internal hop all callers share.
