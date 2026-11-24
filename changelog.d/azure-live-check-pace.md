### Fixed

- The live check against the Azure server keeps under its rate limit, which is 60
  requests a minute per caller there, not the default 120 (measured 2026-11-22: the
  61st request in a minute got a 429). One call every 2 s peaked at 60 to 66 requests a
  minute and met about 20 refusals a run, which its retries absorbed; one every 3.2 s
  stays at 56 at most.
