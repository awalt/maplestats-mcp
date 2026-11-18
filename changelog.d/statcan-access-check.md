### Added

- `statcan_check_access`: which Statistics Canada services answer scripts right
  now. It sends one small request to each service MapleStats reads (WDS, full-table
  files, SDMX, CIMT, The Daily's feeds and archive, indicators, catalogue search,
  microdata files, the Census Profile and RDaaS APIs, the census site) and reports
  each as answers, blocked, error or no answer, with the time checked and the
  tools that use it. It only observes StatCan's Cloudflare check, never answers it.
- A daily workflow (`.github/workflows/statcan-access.yml`) runs the same check and
  fails when StatCan blocks or unblocks a service since
  `docs/findings/statcan-access.json`, so the repo owner gets an email.
