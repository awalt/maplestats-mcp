### Fixed

- `statcan_surveys_*`, `statcan_reference_*`: Cloudflare's bot challenge on
  www150.statcan.gc.ca (every automated request since at least 2026-11-17) is
  reported as the typed "unavailable, do not answer from memory" error, like the
  other StatCan modules, instead of "returned HTTP 403, retry once". These were the
  only two modules reading through `get_with_retry`, which hands a 403 back unread.
  `statcan_surveys_search_surveys` now falls back to IMDB's alphabetical index on
  www23, which still answers, so survey search works during the challenge; before,
  the bare 403 skipped that fallback and the tool failed.
