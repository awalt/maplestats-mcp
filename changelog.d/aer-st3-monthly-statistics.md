### Added

- `aer_st3_get_monthly_statistics`: AER's ST3 Alberta Energy Resource Industries
  Monthly Statistics as tidy monthly rows (period, line, section, value, unit) for
  oil, gas, NGL, ethane, propane, butane, sulphur and oil prices, from 2017 to the
  current year. It reads every workbook the ST3 page links, across the files' layout
  changes (moved month and label columns, the revised 2026 gas report, the 2017-2019
  ZIP archives and the 2023 oil-price .xls). Each year carries AER's run date and the
  months published, and `revision_note` says how monthly releases revise earlier
  months and that the 2026 gas report changed method. Butane 2021 is linked as a PDF
  only, so it is not covered. AER's copyright terms (non-commercial reproduction with
  attribution) are in provenance.
