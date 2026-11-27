# maplestats (Python)

A small Python client for the hosted [MapleStats MCP](https://maplestats.danielstats.io/)
server: Canadian open data from Statistics Canada, the Bank of Canada, CMHC,
provincial agencies and city portals, returned as polars frames with their
citations. It calls the server's `/mcp` endpoint over plain HTTP and needs no
MCP SDK. Design: [`docs/clients.md`](../../docs/clients.md).

Not on PyPI yet. Install from GitHub:

```bash
pip install "git+https://github.com/dsanchezp18/maplestats-mcp#subdirectory=clients/python"
```

## Use

```python
import maplestats as ms

# Find a tool: name, description, arguments and input schema, best match first
ms.search_tools("bank of canada exchange rate")

# Run it and get rows
result = ms.get_data("boc_get_observations", series_names=["FXUSDCAD"], recent=5)
result.data  # polars.DataFrame
result.citation  # ["Source: boc. https://www.bankofcanada.ca/valet/... (queried ...)"]
result.provenance  # source, URL, dates, licence, caveats
result.left_out  # fields of the result beside the rows

# A StatCan series carries its own citation (table, vector, release date)
lfs = ms.get_data("wds_get_data_from_vectors", vector_ids=[2062815], latest_n=12)
lfs.citation

# The raw result, as the server returns it (every field, the whole provenance)
ms.call_tool("boc_get_observations", series_names=["FXUSDCAD"], recent=5)

# The server's compact answer: a list of six or more rows is one CSV text block
ms.call_tool(
    "boc_get_observations", detail="brief", series_names=["FXUSDCAD"], recent=30
)

# Which tools to call for a question that spans sources
ms.plan_query("How has rent in Calgary changed against wages?")

# A script that fetches the same data straight from the publisher, for a
# replication package
code = ms.reproduce_code(
    "boc_get_observations", {"series_names": ["FXUSDCAD"], "recent": 5}
)
print(code["scripts"][0]["code"])
```

`get_data` takes the result's largest list of objects as the rows (a series'
observations become one row each, carrying the series' fields), turns nested
fields into `parent_child` columns and cleans names to snake_case. It does not
convert types: dates stay text.

`get_data` and `call_tool` ask the server for `detail="full"`: every field the
tool returns, the whole provenance and each list of rows as objects, so the
frame has one column for every field (status codes and `context_*` columns
included). The server's own default, `detail="brief"`, writes a list of six or
more rows as one CSV text block and cuts the provenance, which cannot be read
as rows; only `call_tool` takes `detail`, for when you want that compact form.
`detail` needs server 0.6.0 (2026-11-18) or newer: an older server rejects it, so
the client repeats the call without it and gets the full result. A note the
server states once for several series (`shared_notes`) is written back into each
row's `context_notes`. A column that is null on every row (for example
`non_numeric`) is still a column, and a result with no observations comes back
as series metadata rows, not an empty frame.

Errors from the server raise `maplestats.MapleStatsError` with its message,
which says how to fix the call. `maplestats.RateLimited` (a subclass) means the
hosted server's limit of 120 requests a minute; it carries `retry_after`.

## Settings

| Setting | Default |
|---|---|
| `Client(url=...)` or `MAPLESTATS_URL` | `https://mcp.maplestats.danielstats.io/mcp` |
| `Client(token=...)` or `MAPLESTATS_TOKEN` | none (only a self-hosted server with `MAPLE_AUTH_TOKEN` needs one) |
| `Client(timeout=...)` | 240 s (the hosted server lets a call run 230 s) |

```python
with ms.Client(url="http://127.0.0.1:8000/mcp") as local:
    local.search_tools("rent Calgary")
```

## Develop

```bash
uv sync
uv run ruff format . && uv run ruff check .
uv run pyright
uv run pytest                      # recorded responses, no network
MAPLESTATS_LIVE=1 uv run pytest    # adds one call to the hosted server
```

The recorded responses in `tests/fixtures/` come from
`clients/record_fixtures.py`, which calls the hosted server and refreshes the
fixtures of every client.
