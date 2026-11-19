### Added

- `fred_` (3 tools, off unless `FRED_API_KEY` is set): the St. Louis Fed's FRED, a
  publisher separate from Statistics Canada. `fred_search_series` finds a series id,
  `fred_get_series` reads a series' observations and `fred_get_release_dates` lists its
  release's dates, upcoming ones included. FRED needs a free API key that the server's
  operator creates at FRED and sets as `FRED_API_KEY` (MapleStats never ships or asks for
  one); without it the tools are hidden from `search_tools`, `plan_query` and `tools/list`
  (like the `MAPLE_GIS=0` profile) and a call by name explains how to set the key. The key
  is never logged, echoed, cached or recorded: errors name the endpoint, provenance carries
  a placeholder and the request recorders are off for this module. FRED's notice is on every
  result, and a series FRED marks Copyright (a third party owns it) is described but its
  values are not returned. Written from FRED's documentation without a key, so it has not
  met the live API yet; `scripts/smoke_test_fred.py` is the first run to make with a key.
