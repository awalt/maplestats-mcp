# GIS tools: one server, with a switch

Analysis of the pure geospatial tools, 2026-11-16, on `origin/main` (463 tools in 90 modules). The owner approved the plan on 2026-11-17; the decision and its revisit triggers are in [`ROADMAP.md`](../ROADMAP.md#gis-tools). Effort figures below are estimates in engineer-days, not measurements.

## What was measured and what was only read

Measured, in a throwaway worktree: tool counts and listing sizes from `tool_catalogue.json` (tokens approximated as characters divided by 4); the discovery and planner tests and the 129-query benchmark against filtered copies of the catalogue (the repository's own file was only read); `trim_payload` on synthetic geometry payloads; the import time of each module; one read-only `GET` of the hosted server's public `/stats`.

Only read: all code, docstrings, workflows, the Dockerfile, the client libraries and the docs. The Maple Test, the live smoke scripts and every GIS tool against its upstream were not run.

## Classes

PURE: geometry, a layer, a grid, a boundary file or geocoding is the product. HYBRID: tabular or indicator data from a GIS endpoint (ArcGIS REST, WFS, OGC API) or with coordinates only; the answer wanted is rows or figures. Everything else is not GIS. Six PURE tools are borderline (default answer is attributes or a time series, but the source is a polygon composite, a grid or a geocoder): the coverages, `nrcan_nbac_query_fires` and `nrcan_geo_*`.

| Module | Tools | Class |
|---|---:|---|
| `bcgw` | 3 | PURE (OGC WFS on BC's geospatial warehouse; any layer by `type_name`) |
| `statcan` geo, boundaries (`statcan_geo_list_services`, `_get_layer_detail`, `_query_layer`) | 3 | PURE |
| `eccc` coverages (`eccc_coverages_*`) | 3 | PURE, borderline (OGC API Coverages grids) |
| `nrcan_nbac` | 1 | PURE, borderline (burned-area polygon composite) |
| `nrcan_geo` | 2 | PURE, borderline (geolocator and gazetteer) |
| `ab_wildfire` | 8 | 1 PURE (perimeters), 7 HYBRID (fire points, danger, bans, municipal fires, statistics) |
| `cwfis` | 8 | 1 PURE (perimeters), 7 HYBRID (hotspots, stations, forecasts, reports, large fires) |
| `statcan` geo, spatial layers | 3 | HYBRID (deprivation index, housing need, road network) |
| `eccc` GeoMet items | 4 | HYBRID (alerts, observations, AQHI, hydrometric) |
| `arcgis_hub` | 4 | HYBRID (a portal family like CKAN and Socrata) |
| `eps` | 3 | HYBRID |
| `ised` spectrum | 1 | HYBRID |
| `drivebc` | 4 | HYBRID |
| `earthquakes` | 1 | HYBRID |
| `statcan` LODE | 6 | HYBRID |

PURE is 14 tools (3.0%), HYBRID 40 (8.6%) and the rest 409 (88.3%). By description tokens the shares are 3.3%, 8.3% and 88.4%; by full listing (name, title, description and schemas) 21,384, 57,754 and 629,402 tokens. Three modules are wholly PURE: `bcgw`, `nrcan_nbac` and `nrcan_geo`. The exact names are in `src/maplestats_mcp/gis_profile.py`.

## Usage

One `GET` of `/stats` on the hosted server: counters from 2026-11-07 to 2026-11-17, 5,290 calls, of which 2,100 are `search_tools` and `plan_query` and 3,190 are data tools (118 distinct tools).

- PURE tools: 0 calls.
- HYBRID tools: 139 calls (4.4%): `eccc_query_items` 81, `arcgis_hub_search_datasets` 44, `arcgis_hub_query_feature_layer` 8, `arcgis_hub_get_dataset` 4, `eps_summarize_occurrences` 1, `statcan_lode_list_databases` 1.
- Caveats: ten days, early; almost all clients labelled "untracked" (5,273 calls, 371 of them errors) and 17 calls from the chat demo. It cannot separate user traffic from the maintainer's own testing.

## Why the hybrids stay

They are statistics served from a GIS endpoint. The planner routes municipal permit, licence and inspection questions to ArcGIS Hub: ten steps in four admin-record topics (building permits, planning applications, business licences, food inspections), and 68 of 87 place entries list an `arcgis_hub` step (for 61 of them it is the only step, and so the only local portal listed). `eccc_query_items` had 81 live calls and five English discovery cases expect it. Maple Test v4: none of its 72 questions needs a PURE tool, and two climate questions use `eccc_query_items` (read from the fixtures; the test was not run).

## Coupling

- `shared/arcgis.py` (693 lines) is imported by five modules: `arcgis_hub`, `ab_wildfire`, `ised/spectrum`, `statcan/geo` and `eps`. Three of the five are hybrid in product, so it is platform plumbing for ArcGIS-hosted tables, not a GIS-only library. `shared/wfs.py` (229 lines) is imported only by `bcgw`, `cwfis` and `nrcan_nbac`.
- 637 of 1,232 Python files import `maplestats_mcp.shared`, and 53 import `maplestats_mcp.server`: a second server would need a shared core package, not a folder move.
- No GIS-only dependency exists in `pyproject.toml` (LODE hand-codes its Lambert projection), so the image gains nothing from a split today.
- `statcan`, `eccc`, `ab_wildfire` and `cwfis` hold PURE tools beside other tools (and `statcan` and `eccc` share one `resources.py` and `prompts.py`), so moving the class means splitting four packages.
- The planner is not driven by the catalogue. With the PURE class removed, 19 of 129 benchmark plans (14.7%) still named a removed tool (24 of 1,299 steps); with the HYBRID class removed too, 47 plans (36.4%). `nrcan_geo_locate` is recommended by the `places` topic, by the Alberta fire-danger step and by the `earthquakes_search` docstring, so non-GIS flows lean on a PURE tool.
- `reproduce_code` and `reproduce_workbook` call tools through an in-process client, so they work only for tools on the same server object.
- `TOOL_SWITCHES` already hid a tool in three places: the lazy provider listing, the `call_tool` error text and the planner's `_available`. `SERVER_INSTRUCTIONS` and `docs://catalogue` name tools by prefix and by module, and needed templating.

## Cost and benefit of moving the PURE class out

- Retrieval. On the 406 English and French discovery queries whose expected tool is not GIS, a PURE tool was in the top 3 for 3 (0.7%). Removing documents shifts BM25 weights: on the 129 benchmark queries `search_tools` Recall@5 moved from 84.5% to 83.7% with the PURE class removed and to 80.6% with the HYBRID class removed as well; `plan_query` hits were unchanged. One non-GIS case, `CPI-common`, fell from rank 3 to 4.
- Tests. Six test files (770 tests) gave 21 failures with the PURE class removed (2.7%): 16 discovery cases (15 that expected a PURE tool, and `CPI-common`) and five structural checks (the benchmark fixture check, the planner's required arguments, unrouted modules, planned tools registered, the instruction prefixes). The same files now run under both profiles.
- Footprint. A client always sees three tools (about 2,601 tokens) and the instructions (11,442 characters, about 2,860 tokens); the PURE prefixes in the instructions are about 339 characters (about 84 tokens), so a statistics-only model saves about 84 tokens and no tool-list tokens.
- Code and startup. The GIS-class module directories (the nine wholly GIS-class modules, `eccc`, `statcan/geo`, `statcan/lode` and `ised/spectrum`) are 17,772 of 174,338 module source lines (10.2%); the three wholly PURE ones are 2,008 (1.2%). Preloading all 90 modules took 15.2 s on one laptop, and the nine wholly GIS-class modules 0.9 s of that (6%; a single run).
- Isolation is the real benefit of a split: `bcgw` and `nrcan_nbac` parse up to 20 MiB of GeoJSON in the same process and cache as everything else. This was not timed or load-tested.
- Maintenance. 116 of 1,366 commits (8.5%) touched a GIS-class module directory or `shared/arcgis.py` or `shared/wfs.py`; 11 of 93 live smoke scripts are GIS-class, including the two slowest.

## Options considered

| Option | What | Effort | Verdict |
|---|---|---:|---|
| A | Keep one server | 0 | Taken |
| B1 | A default-on switch in the same server (`MAPLE_GIS`) | 1 to 1.5 | Taken, with A |
| B2 | Two `FastMCP` instances behind `/mcp` and `/mcp/stats` | 2 to 4 | Not needed; not verified with FastMCP 4, and module-level state is shared |
| C | A second package in the repository (core, stats, geo) | 8 to 15 | Revisit on a trigger |
| D | A separate repository | 12 to 20, plus ongoing | Not considered further |

A split also needs a handoff for cross-questions (a statistics tool finds a division's code, a geo tool returns its bounding box, a fire-danger tool takes it): the planner would have to name the other server's tools, `search_tools` would have to say a question belongs to the other server, and the user would need both connectors.

## Not done, on purpose

Moving the hybrids (above all `arcgis_hub` and `eccc_query_items`); moving `shared/arcgis.py`; raising any cap (the 200,000-byte response budget, row limits, geometry byte budgets, timeouts) to serve geometry better; splitting the catalogue without making the planner, the instructions and `search_tools` profile-aware in the same change; re-baselining the discovery floors to absorb a split; creating a second package before a geometry-processing dependency exists; hiding the class by default.

## Geometry payloads

A separate finding, independent of the decision above. Geometry is opt-in everywhere (`return_geometry` or `include_geometry` default false), each geometry tool has its own cap (`bcgw` 25 rows and 2,000,000 B of geometry; `nrcan_nbac` 10 rows and 2,000,000 B; `cwfis_get_fire_perimeters` about 400,000 B; `ab_wildfire_get_fire_perimeters` 100 rows, simplified at the source; `statcan_geo_query_layer` and `arcgis_hub_query_feature_layer` up to 2,000 and 1,000 rows with no per-geometry cap), and the server-wide `MAPLE_RESPONSE_MAX_BYTES` (200,000) holds every result.

On synthetic payloads (the real tools were not called) the budget leaves the `geometry` key of `statcan_geo` features intact, but not the `_geometry` key of `arcgis_hub_query_feature_layer` rows: a 60,000-vertex ring was cut to 9,059 vertices, with the cut disclosed in `provenance.limits`. Whether that happens on a real layer is checked in its own change.
