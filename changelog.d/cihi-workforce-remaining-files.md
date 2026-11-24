### Added

- `cihi_workforce_*`: the CIHI health workforce files left out in the first release are now
  read (issue #252). Quick Stats: the hidden data sheets behind its dashboards (supply,
  inflow and outflow, direct care, profiles by profession, graduate migration, hospital
  staffing, vacancies) are tables named after their sheet. The physician workbook's hidden
  `Supply` sheet, the data behind the Table B drop-down, is a table too (`hidden_sheet` in
  `cihi_workforce_list_tables`). The COVID-19, virtual care, Commonwealth Fund survey
  (tables `Q1`, `Q87.2`, ...) and 2016-2020 health care provider workbooks are read: a banner
  row over the header is skipped, zero-width characters in cells are dropped, and "Table 1A"
  titles are recognized. The two `.zip` archives of older releases are listed by their
  workbooks (`archive` names the archive), each read by HTTP range requests without
  downloading the archive. The 40.3 MB NPDB historical utilization 1996-2014 workbook is read
  by parts within the unchanged 30 MiB cap: its Table 2, Table 3 and notes are read, and its
  Table 1 (418,139 rows, 29.5 MB compressed) is listed in `skipped` as too large.

### Changed

- `cihi_workforce_list_tables`: `skipped[].reason` now says why a sheet is left out
  ("interactive: ...", "hidden: ...", "too large: ...") instead of a single word. Hidden sheets
  holding several working tables (the NPDB payments "Percent Change" sheet) and totals checks
  stay out.
