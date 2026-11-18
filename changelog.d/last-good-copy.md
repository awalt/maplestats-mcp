### Added

- When a cached result's refresh is answered with a Cloudflare bot check (as
  Statistics Canada does for scripts since November 2026), the server returns
  the last good copy instead of an error, and its provenance caveats say when
  that copy was fetched. The store is in memory, separate from the cache, and
  capped by `MAPLE_LAST_GOOD_MB` (default 32; 0 turns it off). Idea from
  vrraiv/sixfigures (PR #105), which keeps the last good table on a 403.
