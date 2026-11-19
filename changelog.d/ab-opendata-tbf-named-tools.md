### Added

- Open Alberta: three named tools for Treasury Board and Finance products that were
  reachable only through `ab_opendata_search_datasets` and `ab_opendata_read_resource`
  (#266). `ab_opendata_get_activity_index` returns the monthly Alberta Activity
  Index (January 1981 = 100, 1981 to the latest month). `ab_opendata_get_population_projection`
  returns the population projections to 2051 for Alberta (low, medium and high
  scenarios) or one area of 14 sub-provincial geographies (census divisions, CMAs,
  economic regions, local geographic areas, health and school areas; medium
  scenario), by gender and optionally by single year of age.
  `ab_opendata_get_population_projection_summary` returns the projections summary:
  population, growth, ratios and the components of growth (births, deaths,
  migration). They find the newest edition and the current file themselves and read
  it with the existing Open Alberta reader; all three datasets are under the Open
  Government Licence - Alberta, cited in each result. The budget fiscal plan tables
  are not covered: their workbook answered HTTP 500 on 2026-11-19.
