### Added

- The `calgary_` module (City of Calgary, data.calgary.ca, issue #266): named tools
  for datasets that were reachable only through `socrata_` search before.
  `calgary_list_building_permits` lists building permits (every application since
  1999, refreshed daily) by community, permit class, work class, status, address or
  date; `calgary_summarize_building_permits` counts them, with the housing units they
  add and their estimated cost, by community, class, status, year or month, computed
  by Socrata over every match; `calgary_get_community_populations` gives population,
  occupied dwellings and persons per unit by community from the civic census,
  1968-2019 (the City held no civic census after 2019), or summed for the city.
  Open Government Licence - City of Calgary 2.1, commercial use allowed. The Calgary
  Police Service community crime and disorder statistics are not covered: the City
  took both datasets off public access (they redirect to a login page, checked live
  on 2026-11-19).
