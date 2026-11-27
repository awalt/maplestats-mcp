### Fixed

- Python, R and Julia clients: `get_data` (`ms_get_data` in R) returned a one-row
  or malformed table for any result of six or more rows. The server's default,
  brief answer writes such a list as CSV text, and the clients read only lists
  of objects. Every data call through `call_tool` now sends `detail="full"`, so
  the rows arrive as objects and the whole provenance (query time and caveats)
  is kept. The raw call takes `detail` for the compact form
  (`call_tool(..., detail="brief")`, `ms_call_tool(..., detail = "brief")`).
  The frame has one column for every field the tool returns, including fields a
  brief result leaves out, such as `non_numeric` and a StatCan observation's
  status codes; a column that is null on every row is still a column, and a
  result with no observations comes back as series metadata rows, not an empty
  frame. The test recordings gain 12-row Bank of Canada and WDS results, each
  with its brief twin, so a client that stops asking for full detail now fails
  its tests.
- The same clients on a server older than 0.6.0 (2026-11-18), which rejects
  `detail` on `call_tool`: every data call failed. They now repeat the call once
  without `detail` (the older server answers in full), by the same test
  `search_tools` already used. The refusal must say the argument is unknown, so
  a tool's own error that only mentions "detail" is raised as it is, and
  `search_tools` shares that stricter test.
- The same clients left a note that the server states once for several series
  (`shared_notes`, with "shared_notes[i]" in each series) unresolved: a row's
  `context_notes` read "shared_notes[1]; shared_notes[0]" and `left_out` listed
  `shared_notes`. `get_data` now writes the text back wherever the reference
  stands and no longer reports `shared_notes` as left out; the raw result is as
  the server sent it.
- The same clients' raw call (`call_tool`, `ms_call_tool`) dropped a `detail`
  given for the server's own tools, so `call_tool("search_tools", query=...,
  detail="full")` sent none. It now goes inside that tool's arguments, where
  the tool reads it. `plan_query` takes none, and the server's error says so.
- Julia client: `left_out` listed the rows themselves (`"series"` and
  `"observations"` as `"[list]"`), unlike the Python and R clients, because
  JSON3's lazy views never compare identical. The list the rows came from is now
  told apart by its path.
- R client: the `stringr` requirement is now `stringr (>= 1.5.0)`, the version
  that has the `str_split_1()` the package uses.
