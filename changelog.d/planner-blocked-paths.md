### Added

- `plan_query` and `search_tools` know which StatCan paths answered with the bot check lately. StatCan
  checks some paths of `www150.statcan.gc.ca` and not others (WDS answers; SDMX, the CIMT trade API and the
  catalogue pages do not), so the per-host circuit breaker cannot say which tools are down. A new
  `shared/path_health.py` notes, per path group, when a challenge was last seen and whether the path has
  answered since, from real calls and from a fresh `statcan_check_access` report, for 15 minutes (the
  report's own cache time). While the CIMT path is challenged, a plan step for a `cimt_` tool is kept, listed
  after the working steps, and marked `blocked: true` with a short note and no `call`, and the plan lists the
  same data through WDS first (`wds_get_cube_metadata` on table 12-10-0011-01, labelled as that route); the
  same for the `statcan_reference_` tools and `statcan_pumf_search` / `statcan_pumf_list_files` while the
  catalogue pages are challenged (`wds_search_cubes`). `search_tools` lists such a tool last among the same
  results, with `blocked: true` and a description that names the route. The `sdmx_` tools,
  `statcan_daily_get_releases` and `wds_get_full_table_download` are not marked: each has a route of its own.
  Nothing probes: no request is made for this. With no path seen blocked, both tools answer exactly as before
  (checked byte for byte over the 129 benchmark questions); with the CIMT and catalogue paths blocked, a plan
  is 4 characters shorter on average and a search answer 9 shorter.
