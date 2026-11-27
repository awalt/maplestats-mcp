### Added

- `arcgis_hub_query_file` reads public ArcGIS Hub Document Links on approved data hosts, including Ottawa's current- and previous-year 311 CSVs served as binary downloads. Use `limit=0` to inspect columns and count matching rows. File provenance includes the catalogue page, final download URL and retrieval time.

### Fixed

- Linked table reads reject incomplete downloads, invalid files and scans that cannot finish within the row cap, so a partial file cannot produce a full-file count.
