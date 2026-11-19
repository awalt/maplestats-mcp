### Fixed

- `ilo_compare_countries` and `ilo_get_data`: ILOSTAT's SDMX API (sdmx.ilo.org)
  answered every request with its IIS "403 - Forbidden: Access is denied" page
  on 2026-11-17. Both tools now fall back to the ILO's rplumber data API
  (rplumber.ilo.org), which served the same ILOSTAT tables, for the 13 preset
  comparisons and the datasets behind them (checked live for every key layout:
  sex and age, sex only, sex and currency, currency only, no breakdown). The
  result says which API served it. After an SDMX failure the presets skip
  sdmx.ilo.org for five minutes. `ilo_search_datasets` and `ilo_describe_dataset`
  need the SDMX API and still answer "unavailable" while it is down, and say
  where the comparisons are read from meanwhile.
- `worldbank_get_canada_series`: the World Bank's v2 data endpoint held the
  connection about 60 s and dropped it on 2026-11-17. Series are now read from
  the World Bank's Data360 API (same WDI series, 0.7 to 1.4 s) first, paged 1,000
  rows at a time as that API returns them, and from v2 when Data360 does not
  answer or lacks the indicator. Country names are filled in (English and French)
  since Data360 sends codes only. The catalogue, definitions and topics still come
  from v2.
- `oecd_get_data`: the docstring now carries a quarterly real GDP growth example
  (`DSD_NAMAIN1@DF_QNA_EXPENDITURE_GROWTH_OECD`, key
  `Q.Y.CAN.S1.S1.B1GQ._Z._Z._Z.PC.L.G1.T0102`), the 13-dimension layout the
  dataflow has; a shorter key for `DF_QNA` answered 404 in the research that
  prompted this. The OECD's SDMX API answered a Cloudflare bot challenge from
  2026-11-17 for about a day (MapleStats does not try to pass one) and was back by
  2026-11-19, with Canada's October unemployment rate at 6.7; the key was taken from
  DBnomics' copy of the dataflow and has not been run against the OECD yet.
