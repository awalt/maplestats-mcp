### Added

- `ab_opendata_get_budget_table`: the Alberta budget's fiscal plan tables (Treasury
  Board and Finance), Budget 2017 to Budget 2026 (#266). With no arguments it lists the
  budget's workbooks (economic outlook, revenue, expense, capital plan, tax plan,
  other); a `part` lists its sheets; a `table` (sheet name or title words) is read as
  labelled rows with figures by column ("2026-27 Estimate", "2025-26 Forecast"). The
  Key Energy and Economic Assumptions, the outlook's chart data and the private
  forecasters' benchmarks are in the economic outlook workbook (the outlook itself is a
  PDF). Hidden rows, columns and sheets are left out, as the published page shows them:
  the workbooks keep hidden "#REF!" columns and stale working columns. Open Government
  Licence - Alberta.
- `mb_stats_` (Manitoba Bureau of Statistics, #266): `mb_stats_list_indicators` (the
  Bureau's headline indicators with latest value and change), `mb_stats_list_files`
  (its catalogue of about 150 Excel data tables, PDF bulletins and reports, and links
  to Statistics Canada tables) and `mb_stats_read_file` (one sheet of an Excel table as
  published, with a guessed header row). OpenMB Information and Data Use Licence.
- `on_finance_` (Ontario Ministry of Finance, #266): `on_finance_get_population_projection`
  (projections to 2051 for Ontario in three scenarios, its 6 regions, 49 census
  divisions, 34 public health units and 9 MCCSS regions, by gender and broad, five-year
  or single-year age groups; the fall interim update or the annual release) and
  `on_finance_get_projection_components` (births, deaths, immigration, emigration,
  non-permanent residents, interprovincial migration). Read from the ministry's
  workbooks on data.ontario.ca; Open Government Licence - Ontario.
- `on_finance_get_page_tables`: the tables of two Ontario Ministry of Finance web pages,
  the Ontario Economic Accounts (quarterly real and nominal GDP growth, GDP by
  expenditure, income and industry, implicit price indexes, external factors, release
  calendar) and the Ontario Fact Sheet (population, labour market, economy and trade),
  English or French page. Cells come as published, beside the same cells read as
  numbers. Crown copyright: reproduction for non-commercial purposes, with credit and
  unchanged; each result is marked `commercial_use: not_allowed`.
