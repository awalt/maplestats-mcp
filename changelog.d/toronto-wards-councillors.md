### Added

- City of Toronto: four `toronto_` tools over open.toronto.ca DataStore tables.
  `toronto_get_councillors` lists the mayor and the 25 ward councillors (or one
  ward's) from Elected Officials' Contact Information, 2022-2026 term.
  `toronto_get_ward_neighbourhoods` says which neighbourhoods (140 or 158 model)
  overlap a ward and by how much, measured on the City Wards and Neighbourhoods
  boundaries. `toronto_compare_neighbourhoods` reads one Neighbourhood Profiles
  row for all 140 neighbourhoods, ranked, with an optional share of its parent
  row (the renter share is "Renter" over households by tenure).
  `toronto_get_ward_profile` answers a cross-table question in one call:
  a ward's councillor, its RentSafeTO scores beside the city's with the lowest
  buildings, and each overlapping neighbourhood's 2016 renter share, citing all
  five tables and stating why wards, neighbourhoods and census years do not line
  up. `plan_query` routes Toronto ward and councillor questions to these tools.
  Worked example: `docs/examples/toronto/ward_profile.md`.
