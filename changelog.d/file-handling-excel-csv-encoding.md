### Fixed

- Nine readers opened `.xlsx` workbooks with openpyxl directly and skipped the
  unpacked-size check that the other readers apply (it refuses a workbook whose
  ZIP parts unpack past 400 MB in all, or 32 MB for a part openpyxl loads whole,
  before any of it is read). A small crafted file could hold a parsing worker for
  tens of seconds. The check now covers the Manitoba and Saskatchewan election
  results (`elections_provincial_*`), the historical federal results
  (`elections_results_*`), `finance_canada_*` fiscal tables, the CIPO data
  dictionary (`ised_ip_horizons_get_dictionary`), the NFD dictionary
  (`nfd_describe_table`, which still answers without it), `nl_stats_read_file`,
  the OEB workbooks (`oeb_*`) and the telecom price workbooks (`telecom_prices_*`).
- `ircc_*`, `isc_*`, `elections_financial_returns_*` and the Saskatchewan and
  British Columbia election files decoded UTF-8 and then strict Windows-1252, so a
  file with one of the five bytes Windows-1252 leaves undefined (0x81, 0x8d,
  0x8f, 0x90, 0x9d) failed with a decoding error. They now fall back to latin-1
  as the other CSV readers do. `phac_infobase_*` does the same when a table's
  declared encoding fails.
- CSV files read through the shared CSV reader (CER, GC InfoBase, CDC, CGC,
  NFD, Yukon, elections results) are read as UTF-16 when they start with a
  UTF-16 byte-order mark; they were read as Windows-1252, which gave text full
  of NUL characters and column names that matched nothing.
- A CSV with a quote left open (the rest of the file becomes one field) failed
  with a bare `_csv.Error`; the shared CSV reader and `phac_infobase_*` now
  raise an upstream error that says so.
