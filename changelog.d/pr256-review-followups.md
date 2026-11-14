### Fixed

- `reproduce_code`: for an SDMX call with a transform and an `end_period`, the generated
  R, Python and Julia now stop on the last day of `end_period`, as the tool does
  (`end_period="2024"` on a monthly series keeps 2024-12; the scripts stopped at 2024-01).
- `aer_*` ST98 and `cihi_*` workbook readers now check a workbook's declared unpacked size
  before loading it, as the other `.xlsx` readers do.
- `.xlsx` size limit: the 32 MB per-part cap now applies only to the parts openpyxl loads
  whole (shared strings, styles, workbook, theme). A large embedded image or pivot cache no
  longer fails with a misleading "unpacks to ... XML" error; the total cap is unchanged.
- `electricity_alberta_monthly_summary`: a month AESO has not published (or whose page has
  no readable table) is remembered as missing for 5 minutes, so a range holding a
  never-published month no longer re-requests it on every call; a late-posted month is
  still picked up within minutes.
