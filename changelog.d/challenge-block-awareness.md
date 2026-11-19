### Changed

- A Cloudflare challenge is reported as a block, not an outage. Statistics Canada's
  `www150.statcan.gc.ca` host answered automated clients with a managed challenge (HTTP 403,
  `Cf-Mitigated: challenge`, a page titled "Vérification de sécurité / Security Check") from about
  18:25 UTC on 2026-11-17, and the error of every blocked tool said to "retry once in a minute". The error
  now says, in English and French, not to retry, that the host is challenging automated clients, and which
  sources still answer: the census profile and the CCEI and shared SDMX spaces on `api.statcan.gc.ca`,
  `geo.statcan.gc.ca`, the Bank of Canada, CMHC, the provincial modules and the OECD. The code stays
  `upstream_unavailable`, and `CloudflareChallenge` is still an `UpstreamUnavailable`, so nothing that
  catches it changes; it gains a `host` attribute. The generic hint for a challenge raised by any other
  module no longer says to retry. A challenge still never pauses a host (StatCan's Web Data Service answers
  on the host that challenges SDMX).

### Fixed

- The page check that runs when a 403 carries no `Cf-Mitigated` header now also recognises StatCan's own
  challenge page by its title ("Security Check" or "Vérification de sécurité"), not only "Just a moment";
  a challenge that arrived without the header used to surface as a plain 403 error.
