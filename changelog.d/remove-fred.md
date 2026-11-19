### Removed

- The `fred_` module (FRED, St. Louis Fed), added in 0.7.0: `fred_search_series`,
  `fred_get_series` and `fred_get_release_dates`, with the `FRED_API_KEY` setting
  and FRED's licence notice. It was written from FRED's documentation and never run
  against the live API, and it was offered only where the operator set
  `FRED_API_KEY`, so no hosted server listed it. Nothing replaces it; for US series
  use `fed_` (Federal Reserve Board) or `oecd_`.
