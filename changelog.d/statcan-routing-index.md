### Changed

- Server instructions, Statistics Canada entry: each prefix now names what an
  agent would route on. `wds_` adds revision history (`wds_get_series_as_of`);
  `sdmx_space_` names the shared space's contents (interprovincial trade, rural,
  PCEIP education, Quality of Life); `rdaas_` adds concordances;
  `statcan_indicators_` gets a description; `statcan_pumf_` says it computes
  weighted tables (`statcan_pumf_tabulate`); `statcan_geo_` names the spatial
  layers (deprivation, housing need, roads) next to the census boundaries, and
  under `MAPLE_GIS=0` drops "census boundaries", whose tools that profile hides.
