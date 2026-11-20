### Added

- `cra_tax_stats` module: CRA individual income tax statistics from open.canada.ca
  (Open Government Licence - Canada), harmonized across tax-year editions.
  `cra_tax_stats_get_t1_table` reads the T1 Final Basic Tables (Individual Income Tax
  Return Statistics) for tax years 2018 to 2024: Table 1 by province, 2 by income class,
  3 by source of income, 4 by age and gender, 5 by province of residence, with province
  files for Tables 2 and 4. `cra_tax_stats_get_t1_series` follows one line item across
  every edition. `cra_tax_stats_get_fsa_table` and `cra_tax_stats_get_fsa_series` read
  the statistics by forward sortation area (Tables 1a to 1e and 2) for tax years 2017 to
  2021. `cra_tax_stats_list_tables` lists the editions and the files found in each. File
  names, headers and units change between editions (Table 1 in millions of dollars to
  2021, FSA amounts in dollars to 2020); every amount comes back in thousands of dollars
  with the unit the file published. T1 tax years 2015 to 2017 are left out because their
  file links answer 404.
