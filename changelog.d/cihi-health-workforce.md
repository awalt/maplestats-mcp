### Added

- `cihi_workforce_list_workbooks`, `cihi_workforce_list_tables`, `cihi_workforce_get_table`
  and `cihi_workforce_get_notes` (`modules/cihi/workforce/`, issue #252): CIHI's health
  workforce data tables. The workbooks are listed from CIHI's "Health workforce: Data
  tables" page (a workbook is read only if that page names it): the physician supply,
  distribution and migration tables (2025, with the 2001-2024 and 1971-2000 histories), the
  National Physician Database utilization and payments tables (2024-2025 and the historical
  files), regulated nurses (RNs, LPNs, NPs, RPNs), pharmacists, physiotherapists,
  occupational therapists and personal support workers in Alberta, in English and French.
  Rows come back by jurisdiction, profession, specialty, year, age or sex, each with its
  sheet row (the cell is the column letter plus the row), the table's own notes and CIHI's
  citation line. A mark CIHI prints ('—' no data, 'n/a', 'x' suppressed, 'n/r') is returned
  as that mark, never as zero or blank; a percentage cell comes back as percentage text
  ('90.4%' for the stored 0.904). A filter on a value the table does not have fails with
  the real values, and "Alberta", "Alta." and "Alb." match each other. Not read: Quick Stats
  dashboards,
  the two .zip archives, hidden helper sheets, drop-down tabs, and any workbook over the
  existing 30 MB download cap (the NPDB historical utilization 1996 to 2014, 40 MB, is
  refused). CIHI's Terms of Use limit commercial use and use inside software applications
  without its written authorization: every result carries them in `provenance.caveats`
  and is flagged `commercial_use: not_allowed`.
- `plan_query`: a `health_workforce` topic routes questions about physician, nurse,
  pharmacist, therapist and support worker counts to the new tools, apart from the
  `health` topic's indicators.
