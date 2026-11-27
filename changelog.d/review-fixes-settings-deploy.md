### Fixed

- Three settings that guard the server failed open. `MAPLE_REQUIRE_AUTH=required` started
  an open server (only `1`, `true`, `yes` and `on` turned it on), `MAPLE_QUERY_SERIES=disabled`
  and `MAPLE_PUMF_TABULATE=disabled` left their tools on (only `0`, `false`, `no` and `off`
  turned them off), and a negative `MAPLE_RATE_LIMIT_REQUESTS` became 0, which means no
  limit. An empty `MAPLE_QUERY_SERIES` also turned `wds_query_series` on over HTTP, where
  unset means off.
- `MAPLE_TRANSPORT=stdio` left in the environment of `uvicorn maplestats_mcp.asgi:app` no
  longer makes the HTTP app read as a stdio server (local exports for remote callers when
  `MAPLE_EXPORT_DIR` is set, `wds_query_series` on, no startup preload). A process serving
  HTTP is HTTP whatever the variable says.
- `call_tool` gives the "switched off on this server" guidance for `maplestats.wds_query_series`
  and `WDS_QUERY_SERIES` too, where it answered "Unknown tool".
- The Azure deploys (`docker.yml`) could roll an older commit out after a newer one: two
  pushes in a row each start their own run, and nothing ordered them, so the older
  commit's image could replace the newer one's and stay as `:latest`. Now every run pushes
  its commit's own `:<sha>` tag, `:latest` moves only to the tip of `main`, and a rollout
  is skipped only when the app already runs a later commit (a descendant of the one being
  deployed). If the running image cannot be read or names an unknown commit, the rollout
  goes ahead as before. One gap remains: GitHub keeps a single pending run per concurrency
  group, so a newer commit's pending rollout can still be cancelled by an older commit's run
  that queues after it; the next green push deploys.
- The chat app on Azure now trusts `X-Forwarded-For` for its per-address limits
  (`CHAT_TRUST_PROXY_HEADERS=1` in the deploy), which defaulted on only for Render, so
  every visitor shared the ingress address's limit.
- A `v*` tag (or a release run by hand) now fails unless CI's run on `main` for that commit
  succeeded; the release reran only the Python 3.12 checks, so a commit whose other CI jobs
  failed could still publish. The release waits up to 45 minutes for CI's run to finish and
  says whether there was no run, it did not finish, or it ended in a failure.

### Changed

- An unrecognized value for `MAPLE_REQUIRE_AUTH`, `MAPLE_QUERY_SERIES` or
  `MAPLE_PUMF_TABULATE` now stops the server at startup, naming the variable and the
  accepted values, instead of being read as off or on. The accepted values are `1`, `true`,
  `yes`, `on`, `0`, `false`, `no` and `off`, in any case; an unset or empty variable keeps
  the setting's default. `MAPLE_RATE_LIMIT_REQUESTS` stops the server the same way when it
  is negative or not a whole number (`0` still means no limit); a non-numeric value used to
  fall back to 120 with a warning.
