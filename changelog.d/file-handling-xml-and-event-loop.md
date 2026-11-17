### Fixed

- XML that declares entities (the "billion laughs" expansion) is refused by
  defusedxml before anything is expanded, but four readers caught only the
  parser's `ParseError`, so the refusal reached the client as an untyped error.
  `ourcommons_*` (as "returned no XML"), `statcan_delta_*` (codeset and metadata
  files) and the StatCan SDMX tools now report it like any unreadable XML, and
  `oeb_*` XML files that are malformed or declare a DTD are an upstream error.
- `statcan_delta_*` parsed the metadata XML of a Delta File (up to 80 MB) on the
  server's event loop, and `recalls_*` decoded and read its open-data JSON file
  (up to 64 MB) there too, so every other request waited for seconds while either
  ran. Both now parse in the file-parsing pool. `statcan_cimt_*` code lists moved
  from a thread of the default executor, which DNS lookups share, to the same pool.
