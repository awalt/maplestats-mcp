# ============================================================
# Record MCP responses for the client test suites
# Author: Daniel Sanchez
# Purpose: Call the hosted MapleStats server once per test case and save
#          each raw response body (server-sent events), so the Python, R
#          and Julia client tests run without network access.
# Inputs:  The hosted server (MAPLESTATS_URL overrides the address)
# Outputs: fixtures/*.sse and fixtures/requests.json in every client's test
#          folder that exists
# ============================================================

# %% 0. Setup
import json
import os
from pathlib import Path

import httpx

CLIENTS = Path(__file__).parent
URL = os.environ.get("MAPLESTATS_URL", "https://mcp.maplestats.danielstats.io/mcp")
PROTOCOL = "2025-06-18"
FIXTURE_DIRS = [
    CLIENTS / "python" / "tests" / "fixtures",
    CLIENTS / "r" / "tests" / "testthat" / "fixtures",
    CLIENTS / "julia" / "test" / "fixtures",
]

# Each case is one tools/call: the fixture name, the tool the server runs,
# and its arguments. Tools other than search_tools and plan_query go through
# the call_tool proxy, as the clients send them, with detail="full" beside
# `name` and `arguments`: the server's default, brief result writes a list of
# six or more rows as CSV text, which the clients cannot turn into rows.
# The clients search with detail="full" (input schemas); search_brief is the
# server's default, compact answer (one-line `arguments` signatures).
#
# boc_long and wds_long (12 rows each) and their _brief twins were first written
# on 2026-11-26 without network access: the real server code (call_tool, the
# response budget and the shaping of shared/brief.py) ran in memory over models
# filled by hand, and boc and wds were rebuilt the same way, with their recorded
# values, because they were recorded in brief form. Their values past the
# recorded ones are illustrative. Running this script replaces all of them with
# live recordings.
#
# wds_two (two series of one table) is the case where the server states a note
# shared by several series once, in a top-level `shared_notes` list, and puts
# "shared_notes[i]" in each series' `notes`. It was built the same way, with the
# server's own `shape()` over hand-filled models, so its two series, their values
# and their notes are illustrative.
CASES = [
    ("search_tools", "search_tools", {"query": "bank of canada exchange rate", "detail": "full"}),
    ("search_brief", "search_tools", {"query": "bank of canada exchange rate", "detail": "brief"}),
    ("search_none", "search_tools", {"query": "zzqx", "detail": "full"}),
    ("plan_query", "plan_query", {"question": "Unemployment rate in Alberta"}),
    ("boc", "boc_get_observations", {"series_names": ["FXUSDCAD"], "recent": 3}),
    ("wds", "wds_get_data_from_vectors", {"vector_ids": [2062815], "latest_n": 3}),
    ("tool_error", "boc_get_observations", {"series_names": ["NOPE_XX"], "recent": 3}),
    (
        "reproduce",
        "reproduce_code",
        {
            "tool_name": "boc_get_observations",
            "arguments": {"series_names": ["FXUSDCAD"], "recent": 3},
            "language": "python",
        },
    ),
    ("boc_long", "boc_get_observations", {"series_names": ["FXUSDCAD"], "recent": 12}),
    ("wds_long", "wds_get_data_from_vectors", {"vector_ids": [2062815], "latest_n": 12}),
    ("wds_two", "wds_get_data_from_vectors", {"vector_ids": [2062810, 2062811], "latest_n": 3}),
]
DIRECT = {"search_tools", "plan_query"}

# The two long calls again without `detail`, which is the server's default,
# brief answer: a list of six or more rows is CSV text. The clients' test servers
# answer with these when a request leaves detail="full" out, so a client that
# stopped asking for it would fail its twelve-row tests.
BRIEF_TWINS = ["boc_long", "wds_long"]


def post(client: httpx.Client, body: dict, session: str | None) -> httpx.Response:
    headers = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
    if session:
        headers["mcp-session-id"] = session
        headers["mcp-protocol-version"] = PROTOCOL
    response = client.post(URL, headers=headers, json=body)
    response.raise_for_status()
    return response


# %% 1. Open a session
http = httpx.Client(timeout=240, headers={"user-agent": "maplestats-fixture-recorder"})
initialize = post(
    http,
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "maplestats-fixture-recorder", "version": "0"},
        },
    },
    None,
)
session = initialize.headers["mcp-session-id"]
post(http, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
bodies = {"initialize": initialize.text}
requests = {}

# %% 2. Record each case
for number, (fixture, tool, arguments) in enumerate(CASES, start=2):
    if tool in DIRECT:
        params = {"name": tool, "arguments": arguments}
    else:
        params = {
            "name": "call_tool",
            "arguments": {"name": tool, "arguments": arguments, "detail": "full"},
        }
    body = {"jsonrpc": "2.0", "id": number, "method": "tools/call", "params": params}
    bodies[fixture] = post(http, body, session).text
    requests[fixture] = {"tool": tool, "arguments": arguments}

for number, fixture in enumerate(BRIEF_TWINS, start=len(CASES) + 2):
    request = requests[fixture]
    params = {
        "name": "call_tool",
        "arguments": {"name": request["tool"], "arguments": request["arguments"]},
    }
    body = {"jsonrpc": "2.0", "id": number, "method": "tools/call", "params": params}
    bodies[f"{fixture}_brief"] = post(http, body, session).text

# %% 3. Write fixtures
for folder in FIXTURE_DIRS:
    if not folder.parent.exists():
        continue
    folder.mkdir(exist_ok=True)
    for fixture, text in bodies.items():
        (folder / f"{fixture}.sse").write_text(text, encoding="utf-8", newline="\n")
    manifest = json.dumps(requests, indent=2, ensure_ascii=False) + "\n"
    (folder / "requests.json").write_text(manifest, encoding="utf-8", newline="\n")
