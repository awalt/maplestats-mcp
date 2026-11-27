### Security

- Rate limit: the per-client limit now reads the `X-Forwarded-For` entry (and the
  `MAPLE_CLIENT_IP_HEADER` header) as an address, not as text. `203.0.113.5`,
  `203.0.113.5:51234`, `[::ffff:203.0.113.5]:443` and a padded copy are one caller, and an
  IPv6 address with brackets, a port or a zone counts with its /64 like any other. Behind a
  gateway that appends the source port, each connection used to start a new bucket. An
  entry that is not an address (a hostname, `unknown`, a port past 65535) now keys on the
  connection's own address instead of on the text. The hop that is trusted
  (`MAPLE_TRUSTED_PROXY_HOPS`) has not changed.
- `MAPLE_ALLOWED_ORIGINS`: a subdomain or port wildcard (`https://*.example.org`,
  `http://localhost:*`) is now matched against the parsed Origin, with the scheme and port
  compared exactly and the `*.` standing for whole host labels. An Origin written with user
  information, a path, a query or a fragment, a trailing colon, a port past 65535 or a
  character a host name cannot hold no longer matches (the string match accepted
  `https://evil.org?.example.org`). Exact entries and `*` are unchanged.

### Fixed

- Full-table reads of a StatCan file when the host refuses ranged requests: the inflate
  ceiling is now enforced a bounded step at a time, so one highly compressible chunk can no
  longer inflate far past it in memory before it is checked. A member of the archive that
  is not the data file is now dropped as it downloads, not held whole first.
- Chat demo: "Download CSV" now starts the file with a UTF-8 byte order mark, so Excel
  reads French accents, and a cell that begins with `=`, `+`, `-`, `@`, a tab or a carriage
  return gets a leading apostrophe so a spreadsheet does not run it as a formula (a plain
  number such as `-12.5` is left alone). A cell holding a carriage return is quoted.
- Website search: the query tokenizer in `site.js` now drops only the combining marks the
  server's tokenizer drops (those with a canonical combining class). A variation selector,
  a keycap, a combining grapheme joiner or an Indic vowel sign ends a word in both, where
  the browser used to join the pieces into one.
