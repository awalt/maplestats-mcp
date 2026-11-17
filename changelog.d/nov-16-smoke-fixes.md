### Fixed

- `pmra_search_products` and `pmra_get_product`: the English product extract is now read
  by column name, so a column Health Canada inserts before `Current / Historical` can no
  longer shift status, ingredient or registrant values. A header that has the known first
  column but lacks one of the 16 known names is refused. The French extract and the other
  extracts are still read by position over the leading columns.
- `arcgis_hub_get_dataset`: Kamloops' Photo Grid layer advertises CSV, shapefile,
  GeoJSON and KML exports that all answered HTTP 404 (2026-11-16). The tool now returns
  no links for that one layer and points to `arcgis_hub_query_feature_layer`.
