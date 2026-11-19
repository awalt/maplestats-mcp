### Added

- Site: a City of Toronto page (`toronto.html`, English and French) that
  follows one question through open.toronto.ca with recorded calls: finding
  the RentSafeTO dataset, what its score columns mean in the City's own notes,
  scores by ward, one neighbourhood beside the city, short-term rental
  registrations by ward, and the portal's rules MapleStats keeps.

### Fixed

- `ckan_` tools: a dataset whose licence names an open licence that CKAN does
  not list (the Open Government Licence - Toronto, for one) is now marked
  open. Toronto's portal sets `isopen` to false for its own licence, so every
  Toronto dataset read as "not open" before.
