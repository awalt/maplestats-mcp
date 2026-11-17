### Added

- A `bcer` module (`bcer_` tools) for the BC Energy Regulator's bulk well, production,
  drilling and facility files on iris.bcogc.ca (issue #250). `bcer_list_files` gives each
  file's size, last-modified date and layout notes. `bcer_search_wells` searches the well
  index (about 40,000 wells) by authorization number, UWI, name, location, operator, status,
  fluid, area, formation, class and rig-release date, with each well's operator and surface
  coordinates. `bcer_get_production` returns monthly oil, gas, water and condensate
  production for a well, a list of wells, an operator, an area or formation, or the whole
  province, with monthly totals. `bcer_get_drilling_records`, `bcer_get_fracture_records`
  and `bcer_get_directional_survey` return a well's drilling, completion, test, status,
  hydraulic fracture, perforation and survey records. `bcer_search_facilities` searches the
  facility index and gas plant capacities, and `bcer_get_reference_table` decodes operator,
  area, formation and status codes.
- The 124 MB production zip, the 46 MB drilling zip and the other archives are never
  downloaded or held whole: they are read by HTTP range requests and filtered row by row as
  they inflate, and a read stops at the well's last row (the files are sorted by well
  number, checked on every block). One call reads at most 64 MB compressed in 60 seconds;
  when a ceiling ends a read early the result says so in `complete`, `members_read` and
  `provenance.limits`. No existing cap was raised.
- BCER states no licence for these files, and its website terms say the material may not be
  reproduced or redistributed without the Province's written permission (its Open Data
  Licence is stated only for the GIS portal). Every `bcer_` result therefore carries
  `commercial_use: unknown`, the terms in `provenance.licence` and a caveat to use the data
  for personal or internal analysis and check with BCER before reuse beyond that. The module
  was built with the owner's approval of 2026-11-17, with the terms unresolved.
