### Added

- `ab_economic_get_data` reports two data problems in `provenance.caveats`,
  without dropping rows: a table whose newest row is more than three years old
  (`REACM_EdmRent` ends on 2021-01-01), and rows that share every column but
  `Value`, either repeated (`JobVacanciesQuaterly_14100398_SQL`) or
  disagreeing (`REACM_EdmRent` and `REACM_CgyRent` publish two "Overall Class A
  Net Rent (PSF)" values a year, one near $20 and one in the tens of millions).

### Fixed

- `ab_economic_list_tables` reads the StatCan table number before a `_SQL` or
  `_stage` suffix (`JobVacanciesQuaterly_14100398_SQL` is 14100398). Seven-digit
  endings, which the dashboard truncated, are still left empty.
