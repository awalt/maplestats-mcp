# maplestats (R)

A small R client for the hosted [MapleStats MCP](https://maplestats.danielstats.io/)
server: Canadian open data from Statistics Canada, the Bank of Canada, CMHC,
provincial agencies and city portals, returned as tibbles with their citation
attached. It calls the server's `/mcp` endpoint with httr2 and needs no MCP
SDK. Design: [`docs/clients.md`](../../docs/clients.md).

Not on CRAN yet. Install from GitHub:

```r
pak::pak("dsanchezp18/maplestats-mcp/clients/r")
```

## Use

```r
library(maplestats)

# Find a tool: name, description, arguments and input schema, best match first
ms_search_tools("bank of canada exchange rate")

# Run it and get rows. Wrap a length-one vector in I() when the tool
# expects an array.
usd_cad <- ms_get_data(
  "boc_get_observations",
  series_names = I("FXUSDCAD"),
  recent = 5
)
attr(usd_cad, "citation")
attr(usd_cad, "provenance")$licence

# A StatCan series carries its own citation (table, vector, release date)
unemployment <- ms_get_data(
  "wds_get_data_from_vectors",
  vector_ids = I(2062815),
  latest_n = 12
)
attr(unemployment, "citation")

# The raw result, as the server returns it (every field, the whole provenance)
ms_call_tool("boc_get_observations", series_names = I("FXUSDCAD"), recent = 5)

# The server's compact answer: a list of six or more rows is one CSV text block
ms_call_tool(
  "boc_get_observations",
  series_names = I("FXUSDCAD"),
  recent = 30,
  detail = "brief"
)

# Which tools to call for a question that spans sources
ms_plan_query("How has rent in Calgary changed against wages?")

# A script that fetches the same data straight from the publisher, for a
# replication package
code <- ms_reproduce_code(
  "boc_get_observations",
  list(series_names = I("FXUSDCAD"), recent = 5)
)
writeLines(code$scripts[[1]]$code, "code/cleaning/00_download_boc.R")
```

`ms_get_data()` takes the result's largest list of objects as the rows (a
series' observations become one row each, carrying the series' fields), turns
nested fields into `parent_child` columns and cleans names to snake_case, as
`janitor::clean_names()` does. It does not convert types: parse dates with
`lubridate::ymd()` yourself. The attributes are `citation`, `provenance`,
`left_out` (fields of the result beside the rows), `tool` and `arguments`;
most dplyr verbs drop them, so read them before transforming.

`ms_get_data()` and `ms_call_tool()` ask the server for `detail = "full"`:
every field the tool returns, the whole provenance and each list of rows as
objects, so the tibble has one column for every field (status codes and
`context_*` columns included). The server's own default, `detail = "brief"`,
writes a list of six or more rows as one CSV text block and cuts the
provenance, which cannot be read as rows; only `ms_call_tool()` takes
`detail`, for when you want that compact form. `detail` needs server 0.6.0
(2026-11-18) or newer: an older server rejects it, so the client repeats the
call without it and gets the full result. A note the server states once for
several series (`shared_notes`) is written back into each row's
`context_notes`. A column that is null on every row (for example
`non_numeric`) is still a column, and a result with no observations comes back
as series metadata rows, not an empty tibble.

Errors are conditions of class `maplestats_error` with the server's message,
which says how to fix the call. A `maplestats_rate_limited` error (the hosted
server allows 120 requests a minute) carries `retry_after`.

## Settings

| Setting | Default |
|---|---|
| `ms_client(url = )` or `MAPLESTATS_URL` | `https://mcp.maplestats.danielstats.io/mcp` |
| `ms_client(token = )` or `MAPLESTATS_TOKEN` | none (only a self-hosted server with `MAPLE_AUTH_TOKEN` needs one) |
| `ms_client(timeout = )` | 240 s (the hosted server lets a call run 230 s) |

```r
local <- ms_client(url = "http://127.0.0.1:8000/mcp")
ms_search_tools("rent Calgary", client = local)
```

## Develop

```r
styler::style_pkg(indent_by = 2, scope = "tokens")
lintr::lint_package()
roxygen2::roxygenise()
testthat::test_local()        # recorded responses, no network
```

Set `MAPLESTATS_LIVE=1` to add one call to the hosted server. The recorded
responses in `tests/testthat/fixtures/` come from `clients/record_fixtures.py`,
which refreshes the fixtures of every client.
