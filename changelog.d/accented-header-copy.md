### Fixed

- A source that answered with an accented character in a header value (DFO's
  landings file sent an `é` on 2026-11-19) no longer fails with
  `UnicodeEncodeError` in tools that read with a size cap. The answer's headers
  are now copied as the bytes received.
