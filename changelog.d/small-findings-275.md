### Fixed

- `cmhc_get_table_data`: `table_name` no longer carries the trailing spaces CMHC
  pads some table names with (for example "Historical Average Rents by Bedroom
  Type  "); the name is stripped where it is read from the portal, so it and the
  `citation` agree.
- `jobbank_get_wages`: `provenance.coverage` now says how many of the published
  cells are economic regions that repeat their province's wage
  (`estimate_geography` "provincial"), so "3 with a published wage" for NOC 21211
  in Alberta no longer reads as three separate estimates when Edmonton repeats
  Alberta's wage and only Alberta and Calgary are distinct. `published_count`
  keeps its meaning (cells with a published wage), and its schema description
  now says it includes those repeats.
- `plan_query`: a province's own tools (`bc_transit_*`, `drivebc_*`, `bc_env_*`,
  `bc_lobbyists_*`, `ab_wildfire_*`, `aer_*`) no longer appear in the plan for a
  question that names only places in other provinces: "transit alerts in
  Calgary" listed BC Transit and DriveBC. Each city the planner knows is now
  mapped to its province (`places.CITY_PROVINCES`). The tools stay when the
  question names no place, names the province or one of its cities, or names a
  place whose province is not on record.
