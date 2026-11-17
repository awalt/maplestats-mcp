### Fixed

- `reproduce_code` no longer replays an arbitrary request for a tool that fans
  out over ids. When a tool made several requests to one endpoint that differ
  only in an id or a year (13 provinces' lists, one CSV per year) and its
  result's URL names none of them, `reproduce_code` fell back to the last
  request recorded, which depends on the order the parallel requests started in
  and so changed from run to run. It now returns no script and a note: "This
  result combines N requests to one endpoint family (...), so a script cannot
  say which one to repeat. Call the tool again with an argument that selects
  one of them, then reproduce that call." (also in French). A result that names
  one of the requests, one request to the endpoint, and paging through one
  endpoint behave as before.
