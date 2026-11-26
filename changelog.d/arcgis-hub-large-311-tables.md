### Fixed

- `arcgis_hub_query_file` now accepts downloads and uncompressed ZIP members
  up to 64 MiB, covering Ottawa's 2022 service request archive and annual CSVs.
  CSV parsing keeps pipes in bilingual column names and reads the decoded table
  incrementally.
