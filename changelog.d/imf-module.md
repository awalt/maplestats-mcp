### Added

- `imf_` (4 tools): International Monetary Fund data (api.imf.org SDMX 2.1, no key), a
  publisher separate from Statistics Canada whose figures are labelled as the IMF's in
  every result. `imf_search_datasets` finds a dataset (consumer prices, exchange rates,
  balance of payments, labour statistics, national accounts, trade by partner, World
  Economic Outlook, commodity prices); `imf_describe_dataset` gives its key layout and
  codes (French code names with `lang="fr"`); `imf_search_series` lists Canada's series
  in it with the latest value of each; `imf_get_data` reads observations by SDMX key with
  period filters, capped at 200 series and 10,000 rows. Checked live: Canada's CPI index
  was 170.0 for September 2026 (the IMF runs about a month behind) and the October 2026
  World Economic Outlook has real GDP growth of 1.12 per cent for 2026. The IMF's terms
  allow copying with the IMF credited but ask for permission for commercial reuse, so each
  result is flagged `commercial_use: not_allowed` and carries them. The planner offers the
  tools after the StatCan steps for questions that name the IMF or the World Economic
  Outlook.
