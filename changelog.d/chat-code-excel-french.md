### Added

- The chat demo has "Get the code" and "Download Excel" buttons under each answer that fetched
  data. "Get the code" shows the R, Python, Stata, Julia and Excel Power Query scripts that
  `reproduce_code` writes for a data call behind the answer, with copy and download buttons;
  "Download Excel" saves the rows as an .xlsx from `reproduce_workbook` (base64 delivery). With
  several calls behind an answer, a list picks which one. The chat service asks the MCP server
  through `call_tool` (new `POST /api/code` and `POST /api/workbook`); no model is called, and
  the exports have their own hourly limit per address (`CHAT_EXPORT_PER_HOUR`, 30).
- The chat demo has a French interface: a switch in the header (the first visit follows the
  browser's language) puts every string of the page in French, and the service then answers
  limits and errors in French and tells the model to pass `lang="fr"` to `plan_query` and every
  tool.
